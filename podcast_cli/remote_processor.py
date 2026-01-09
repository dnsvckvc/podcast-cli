import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

from .remote_api_client import RemoteAPIClient
from .output_manager import OutputManager
from .cli_processor import ProcessingResult  # Reuse the same result class
from .performance_tracker import PerformanceTracker, BatchPerformanceTracker


class RemoteProcessor:
    """
    Processor for remote API-based podcast processing.
    
    Provides the same interface as CLIProcessor but uses the remote Hugging Face API
    instead of local processing components.
    """

    def __init__(self, output_manager: OutputManager, api_url: str = None, verbose: bool = False):
        """
        Initialize remote processor.
        
        Args:
            output_manager (OutputManager): Output manager instance
            api_url (str): Custom API URL (optional)
            verbose (bool): Enable verbose logging
        """
        self.output_manager = output_manager
        self.verbose = verbose
        
        # Setup logging
        self.logger = self._setup_logger()
        
        # Initialize API client
        try:
            self.api_client = RemoteAPIClient(api_url=api_url)
            # Test authentication on initialization
            self.api_client.authenticate()
            self.logger.info("Remote API processor initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize remote API client: {e}")
            raise

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for remote processing."""
        logger = logging.getLogger("remote_processor")
        
        if self.verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        
        # Only add handler if none exists
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger

    def validate_input(self, source_url: str, platform: str, episode_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate input parameters using the remote API.
        
        Args:
            source_url (str): Source URL to validate
            platform (str): Platform type ('youtube' or 'rss')
            episode_name (Optional[str]): Episode name for RSS feeds
            
        Returns:
            Dict[str, Any]: Validation result
        """
        try:
            # Use API validation
            validation_result = self.api_client.validate_url(source_url, platform)
            
            if validation_result["valid"]:
                return {
                    "valid": True,
                    "platform": platform,
                    "source_url": source_url,
                    "episode_name": episode_name
                }
            else:
                return {
                    "valid": False,
                    "error": validation_result.get("error", "URL validation failed")
                }
                
        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation error: {str(e)}"
            }

    def process_single(self, source_url: str, platform: str, 
                      options: Dict[str, Any]) -> ProcessingResult:
        """
        Process a single podcast episode using the remote API.
        
        Args:
            source_url (str): Source URL for the episode
            platform (str): Platform type ('youtube' or 'rss')
            options (Dict[str, Any]): Processing options
            
        Returns:
            ProcessingResult: Result of processing
        """
        # Initialize performance tracking
        episode_id = f"{platform}_{hash(source_url) % 1000000}"
        perf_tracker = PerformanceTracker(
            episode_id=episode_id,
            processing_mode="remote",
            verbose=self.verbose
        )
        perf_tracker.start_processing()
        
        try:
            # Stage 1: Validation
            perf_tracker.start_stage("validation")
            validation = self.validate_input(
                source_url, platform, options.get("episode_name")
            )
            if not validation["valid"]:
                perf_tracker.stop_stage(error=validation.get('error'))
                perf_tracker.stop_processing(success=False, error="Validation failed")
                return ProcessingResult(
                    success=False,
                    error=f"Validation failed: {validation.get('error', 'Unknown error')}",
                    performance_tracker=perf_tracker
                )
            perf_tracker.stop_stage()
            
            episode_name = validation.get("episode_name")
            
            # Check if already processed (unless force reprocess)
            if not options.get("force_reprocess", False):
                existing_path = self.output_manager.is_already_processed(
                    source_url, platform, episode_name
                )
                if existing_path:
                    self.logger.info(f"Episode already processed at {existing_path}")
                    perf_tracker.stop_processing(success=True)
                    return ProcessingResult(
                        success=True,
                        episode_path=existing_path,
                        metadata={"message": "Already processed (remote)"},
                        performance_tracker=perf_tracker
                    )
            
            self.logger.info(f"Starting remote processing: {source_url}")
            
            # Handle API limitations for processing modes
            if options.get("transcribe_only"):
                self.logger.warning("Remote API doesn't support transcribe-only mode, processing normally")
            
            if options.get("summarize_only"):
                return ProcessingResult(
                    success=False,
                    error="Remote API doesn't support summarize-only mode (no access to existing transcripts)"
                )
            
            # Stage 2: Submit task to API
            perf_tracker.start_stage("api_submission")
            try:
                task_id = self.api_client.submit_task(
                    source_url=source_url,
                    platform=platform,
                    episode_name=episode_name,
                    detail_level=options.get("detail_level", 0.5)
                )
                perf_tracker.stop_stage(task_id=task_id, detail_level=options.get("detail_level", 0.5))
            except Exception as e:
                # Check if it's an authentication error and provide helpful message
                error_msg = str(e)
                if "401" in error_msg or "UNAUTHORIZED" in error_msg.upper():
                    error_msg = f"Authentication failed - token may have expired: {error_msg}"
                    self.logger.warning("Token expiration detected, automatic retry should handle this")
                
                perf_tracker.stop_stage(error=error_msg)
                perf_tracker.stop_processing(success=False, error=f"Task submission failed: {error_msg}")
                return ProcessingResult(
                    success=False,
                    error=f"Task submission failed: {error_msg}",
                    performance_tracker=perf_tracker
                )
            
            # Stage 3: Remote processing (wait for completion)
            perf_tracker.start_stage("remote_processing")
            
            def progress_callback(status, progress, message):
                if self.verbose:
                    self.logger.info(f"Task {task_id}: {status} - {progress}% - {message}")
            
            try:
                result = self.api_client.wait_for_completion(
                    task_id=task_id,
                    max_wait_minutes=30,
                    progress_callback=progress_callback if self.verbose else None
                )
                perf_tracker.stop_stage(
                    task_id=task_id,
                    api_endpoint=self.api_client.api_url
                )
            except Exception as e:
                perf_tracker.stop_stage(error=str(e))
                perf_tracker.stop_processing(success=False, error=f"Task processing failed: {str(e)}")
                return ProcessingResult(
                    success=False,
                    error=f"Task processing failed: {str(e)}",
                    performance_tracker=perf_tracker
                )
            
            # Create metadata from API result
            metadata = {
                "title": result.get("title", "Unknown Title"),
                "channel": result.get("channel", "Unknown Channel"),
                "duration_string": result.get("duration_string", "Unknown"),
                "release_date": result.get("release_date", "Unknown"),
                "thumbnail": result.get("thumbnail"),
                "source_url": source_url,
                "platform": platform,
                "processed_via": "remote_api",
                "task_id": task_id
            }
            
            # Create episode folder
            episode_path = self.output_manager.create_episode_folder(
                source_url, metadata, platform
            )
            
            # Stage 4: Save files
            perf_tracker.start_stage("file_operations")
            
            # Set episode metadata for performance tracking
            perf_tracker.performance.episode_metadata = metadata
            
            files_created = self.output_manager.save_episode_files(
                episode_path=episode_path,
                audio_path=None,  # API doesn't provide audio file
                transcript=result.get("transcript", ""),
                summary=result.get("summary", ""),
                metadata=metadata,
                processing_options=options
            )
            
            perf_tracker.stop_stage(
                files_created=len(files_created),
                output_path=str(episode_path)
            )
            
            perf_tracker.stop_processing(success=True)
            
            # Save performance data after processing is complete
            perf_tracker.save_performance_data(episode_path)
            
            self.logger.info(f"Successfully processed episode via API: {episode_path.name}")
            
            # Print performance report if verbose
            if self.verbose:
                perf_tracker.print_performance_report()
            
            return ProcessingResult(
                success=True,
                episode_path=episode_path,
                metadata=metadata,
                files_created=files_created,
                performance_tracker=perf_tracker
            )
            
        except Exception as e:
            self.logger.exception(f"Unexpected error in remote processing: {source_url}")
            perf_tracker.stop_processing(success=False, error=f"Unexpected error: {str(e)}")
            return ProcessingResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                performance_tracker=perf_tracker
            )

    def process_batch(self, sources: List[Dict[str, str]], 
                     options: Dict[str, Any]) -> List[ProcessingResult]:
        """
        Process multiple podcast episodes using the remote API.
        
        Note: Remote processing is inherently sequential due to API constraints.
        The parallel option is ignored for remote processing.
        
        Args:
            sources (List[Dict[str, str]]): List of source dictionaries
            options (Dict[str, Any]): Processing options
            
        Returns:
            List[ProcessingResult]: Results for each episode
        """
        # Initialize batch performance tracking
        batch_tracker = BatchPerformanceTracker(verbose=self.verbose)
        batch_tracker.start_batch()
        
        results = []
        total = len(sources)
        
        self.logger.info(f"Starting remote batch processing of {total} episodes")
        
        if options.get("parallel", 1) > 1:
            self.logger.warning("Remote API processing is sequential - parallel option ignored")
        
        for i, source in enumerate(sources, 1):
            self.logger.info(f"Processing {i}/{total}: {source.get('url', 'Unknown URL')}")
            
            result = self.process_single(
                source_url=source["url"],
                platform=source["platform"],
                options={**options, "episode_name": source.get("episode_name")}
            )
            
            results.append(result)
            
            # Add performance data to batch tracker
            if result.performance_tracker:
                batch_tracker.add_episode_performance(result.performance_tracker.performance)
            
            if result.success:
                self.logger.info(f"✓ Success: {result.episode_path.name if result.episode_path else 'Unknown'}")
            else:
                self.logger.error(f"✗ Failed: {result.error}")
        
        batch_tracker.stop_batch()
        
        success_count = sum(1 for r in results if r.success)
        self.logger.info(f"Remote batch processing completed: {success_count}/{total} successful")
        
        # Print batch performance summary
        if self.verbose:
            batch_tracker.print_batch_summary()
        
        return results

    def get_component_info(self) -> Dict[str, str]:
        """Get information about remote processing components."""
        try:
            api_info = self.api_client.get_api_info()
            return {
                "processing_mode": "remote_api",
                "api_url": self.api_client.api_url,
                "api_version": api_info.get("version", "unknown"),
                "api_status": api_info.get("status", "unknown")
            }
        except Exception as e:
            return {
                "processing_mode": "remote_api",
                "api_url": self.api_client.api_url,
                "error": str(e)
            }