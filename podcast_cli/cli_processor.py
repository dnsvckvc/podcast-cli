import os
import logging
import tempfile
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

# Import existing components
from .models.downloaders.yt_downloader import YTDownloader
from .models.downloaders.rss_feed_downloader import RSS_Feed_Downloader
from .models.transcribers.salad_transcriber import SaladTranscriber
from .models.transcribers.whisper_transcriber import WhisperTranscriber
from .models.transcribers.local_whisper_transcriber import LocalWhisperTranscriber
from .models.summarizers.openai_summarizer import OpenAI_Summarizer
from .utils.validators import URLValidator, InputValidator
from .output_manager import OutputManager
from .performance_tracker import PerformanceTracker, BatchPerformanceTracker


@dataclass
class ProcessingResult:
    """Result of processing a single episode."""
    success: bool
    episode_path: Optional[Path] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    files_created: Optional[Dict[str, Path]] = None
    performance_tracker: Optional[PerformanceTracker] = None


class CLIProcessor:
    """
    Main processor for CLI-based podcast processing.
    
    Handles downloading, transcription, and summarization of podcast content
    using the existing modular components in a local processing environment.
    """

    def __init__(self, config: Dict[str, Any], output_manager: OutputManager, verbose: bool = False):
        """
        Initialize CLI processor with configuration and output manager.
        
        Args:
            config (Dict[str, Any]): Configuration dictionary
            output_manager (OutputManager): Output manager instance
            verbose (bool): Enable verbose logging
        """
        self.config = config
        self.output_manager = output_manager
        self.verbose = verbose
        
        # Setup logging
        self.logger = self._setup_logger()
        
        # Initialize components
        self._init_components()

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for CLI processing."""
        logger = logging.getLogger("cli_processor")
        
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

    def _init_components(self):
        """Initialize downloader, transcriber, and summarizer components."""
        # Initialize downloaders
        self.yt_downloader = YTDownloader(config=self.config["youtube"])
        self.rss_downloader = RSS_Feed_Downloader(config=self.config["rss_feed"])
        
        # Initialize transcriber with fallback priority
        transcriber_type = self.config.get("transcriber", "auto")
        self.transcriber = self._init_transcriber(transcriber_type)
        
        # Initialize summarizer (only if needed)
        self.summarizer = None  # Will be initialized on demand
        
        self.logger.info(f"Initialized CLI processor with {type(self.transcriber).__name__}")

    def _init_transcriber(self, transcriber_type: str):
        """Initialize transcriber with intelligent fallback based on available credentials."""
        import os
        
        if transcriber_type == "auto":
            # Auto-select based on available credentials, prefer local
            if os.getenv("SALAD_API_KEY") and os.getenv("SALAD_ORGANIZATION"):
                self.logger.info("Auto-selected Salad transcriber (API credentials found)")
                return SaladTranscriber(config=self.config.get("salad", {}))
            elif os.getenv("OPENAI_API_KEY"):
                self.logger.info("Auto-selected OpenAI Whisper transcriber (API key found)")
                return WhisperTranscriber(config=self.config.get("whisper", {}))
            else:
                self.logger.info("Auto-selected local Whisper transcriber (no API keys required)")
                return LocalWhisperTranscriber(config=self.config.get("local_whisper", self.config.get("whisper", {})))
        
        elif transcriber_type == "salad":
            return SaladTranscriber(config=self.config["salad"])
        elif transcriber_type == "whisper":
            return WhisperTranscriber(config=self.config["whisper"])  
        elif transcriber_type == "local_whisper":
            return LocalWhisperTranscriber(config=self.config.get("local_whisper", self.config.get("whisper", {})))
        else:
            # Fallback to local whisper for unknown types
            self.logger.warning(f"Unknown transcriber type '{transcriber_type}', falling back to local Whisper")
            return LocalWhisperTranscriber(config=self.config.get("local_whisper", self.config.get("whisper", {})))

    def _init_summarizer(self):
        """Initialize summarizer on demand."""
        if self.summarizer is None:
            self.summarizer = OpenAI_Summarizer(config=self.config["openai"])
            self.logger.info("Initialized OpenAI summarizer")
        return self.summarizer

    def validate_input(self, source_url: str, platform: str, episode_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate input parameters before processing.
        
        Args:
            source_url (str): Source URL to validate
            platform (str): Platform type ('youtube' or 'rss')
            episode_name (Optional[str]): Episode name for RSS feeds
            
        Returns:
            Dict[str, Any]: Validation result
        """
        # Validate platform
        platform_validation = InputValidator.validate_platform(platform)
        if not platform_validation["valid"]:
            return platform_validation
        
        platform = platform_validation["value"]
        
        # Validate URL based on platform
        if platform == "youtube":
            url_validation = URLValidator.validate_youtube_url(source_url)
        else:  # rss
            url_validation = URLValidator.validate_rss_url(source_url)
        
        if not url_validation["valid"]:
            return url_validation
        
        # Validate episode name for RSS
        if platform == "rss":
            episode_validation = InputValidator.validate_episode_name(episode_name, platform)
            if not episode_validation["valid"]:
                return episode_validation
            episode_name = episode_validation["value"]
        
        return {
            "valid": True,
            "platform": platform,
            "source_url": source_url,
            "episode_name": episode_name
        }

    def process_single(self, source_url: str, platform: str, 
                      options: Dict[str, Any]) -> ProcessingResult:
        """
        Process a single podcast episode.
        
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
            processing_mode="local",
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
            
            # Check if already processed
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
                        metadata={"message": "Already processed"},
                        performance_tracker=perf_tracker
                    )
            
            self.logger.info(f"Starting processing: {source_url}")
            
            # Stage 2: Download/Process audio
            perf_tracker.start_stage("download")
            downloader = self.yt_downloader if platform == "youtube" else self.rss_downloader
            
            self.logger.info("Downloading audio...")
            try:
                audio_path, metadata = downloader.download_episode(source_url, episode_name)
                metadata["source_url"] = source_url
                metadata["platform"] = platform
                perf_tracker.stop_stage(
                    audio_path=audio_path,
                    title=metadata.get("title", "Unknown"),
                    duration=metadata.get("duration_string", "Unknown")
                )
            except Exception as e:
                perf_tracker.stop_stage(error=str(e))
                perf_tracker.stop_processing(success=False, error=f"Download failed: {str(e)}")
                return ProcessingResult(
                    success=False,
                    error=f"Download failed: {str(e)}",
                    performance_tracker=perf_tracker
                )
            
            # Create episode folder
            episode_path = self.output_manager.create_episode_folder(
                source_url, metadata, platform
            )
            
            # Set episode metadata for performance tracking
            perf_tracker.performance.episode_metadata = metadata
            
            transcript = ""
            summary = ""
            
            # Stage 3: Transcription (if requested)
            if options.get("transcribe", True) and not options.get("summarize_only", False):
                perf_tracker.start_stage("transcription")
                self.logger.info("Transcribing audio...")
                try:
                    transcript = self.transcriber.transcribe(
                        audio_path=audio_path, 
                        video_id=metadata.get("video_id", "unknown")
                    )
                    perf_tracker.stop_stage(
                        transcriber=type(self.transcriber).__name__,
                        transcript_length=len(transcript),
                        audio_duration=metadata.get("duration_string", "Unknown")
                    )
                    self.logger.info("Transcription completed")
                except Exception as e:
                    perf_tracker.stop_stage(error=str(e))
                    perf_tracker.stop_processing(success=False, error=f"Transcription failed: {str(e)}")
                    return ProcessingResult(
                        success=False,
                        error=f"Transcription failed: {str(e)}",
                        episode_path=episode_path,
                        metadata=metadata,
                        performance_tracker=perf_tracker
                    )
            
            # Stage 4: Summarization (if requested and we have transcript)
            if options.get("summarize", True) and not options.get("transcribe_only", False):
                # Use existing transcript if available
                if not transcript and options.get("summarize_only"):
                    transcript_file = episode_path / "transcript.txt"
                    if transcript_file.exists():
                        with open(transcript_file, 'r', encoding='utf-8') as f:
                            transcript = f.read()
                    else:
                        perf_tracker.stop_processing(success=False, error="No transcript found for summarize-only mode")
                        return ProcessingResult(
                            success=False,
                            error="No transcript found for summarize-only mode",
                            episode_path=episode_path,
                            metadata=metadata,
                            performance_tracker=perf_tracker
                        )
                
                if transcript:
                    perf_tracker.start_stage("summarization")
                    self.logger.info("Generating summary...")
                    try:
                        # Initialize summarizer on demand
                        summarizer = self._init_summarizer()
                        summary = summarizer.summarize(
                            transcript, 
                            detail=options.get("detail_level", 0.5)
                        )
                        perf_tracker.stop_stage(
                            detail_level=options.get("detail_level", 0.5),
                            summary_length=len(summary),
                            transcript_length=len(transcript)
                        )
                        self.logger.info("Summary generation completed")
                    except Exception as e:
                        perf_tracker.stop_stage(error=str(e))
                        perf_tracker.stop_processing(success=False, error=f"Summarization failed: {str(e)}")
                        return ProcessingResult(
                            success=False,
                            error=f"Summarization failed: {str(e)}",
                            episode_path=episode_path,
                            metadata=metadata,
                            performance_tracker=perf_tracker
                        )
            
            # Stage 5: Save files
            perf_tracker.start_stage("file_operations")
            files_created = self.output_manager.save_episode_files(
                episode_path=episode_path,
                audio_path=audio_path,
                transcript=transcript,
                summary=summary,
                metadata=metadata,
                processing_options=options
            )
            
            # Cleanup temporary files
            if audio_path and "/tmp/" in audio_path:
                temp_dir = os.path.dirname(audio_path)
                self.output_manager.cleanup_temp_files(temp_dir)
            
            perf_tracker.stop_stage(
                files_created=len(files_created),
                output_path=str(episode_path)
            )
            
            perf_tracker.stop_processing(success=True)
            
            # Save performance data after processing is complete
            perf_tracker.save_performance_data(episode_path)
            
            self.logger.info(f"Successfully processed episode: {episode_path.name}")
            
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
            self.logger.exception(f"Unexpected error processing {source_url}")
            perf_tracker.stop_processing(success=False, error=f"Unexpected error: {str(e)}")
            return ProcessingResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                performance_tracker=perf_tracker
            )

    def process_batch(self, sources: List[Dict[str, str]], 
                     options: Dict[str, Any]) -> List[ProcessingResult]:
        """
        Process multiple podcast episodes.
        
        Args:
            sources (List[Dict[str, str]]): List of source dictionaries with 'url', 'platform', 'episode_name'
            options (Dict[str, Any]): Processing options
            
        Returns:
            List[ProcessingResult]: Results for each episode
        """
        # Initialize batch performance tracking
        batch_tracker = BatchPerformanceTracker(verbose=self.verbose)
        batch_tracker.start_batch()
        
        results = []
        total = len(sources)
        
        self.logger.info(f"Starting batch processing of {total} episodes")
        
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
        self.logger.info(f"Batch processing completed: {success_count}/{total} successful")
        
        # Print batch performance summary
        if self.verbose:
            batch_tracker.print_batch_summary()
        
        return results

    def get_component_info(self) -> Dict[str, str]:
        """Get information about initialized components."""
        return {
            "transcriber": type(self.transcriber).__name__,
            "summarizer": type(self.summarizer).__name__,
            "youtube_downloader": type(self.yt_downloader).__name__,
            "rss_downloader": type(self.rss_downloader).__name__
        }