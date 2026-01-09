import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .models.downloaders.yt_downloader import YTDownloader
from .models.downloaders.rss_feed_downloader import RSS_Feed_Downloader
from .models.transcribers.salad_transcriber import SaladTranscriber
from .models.summarizers.openai_summarizer import OpenAI_Summarizer
from .utils.validators import URLValidator, InputValidator
from .output_manager import OutputManager
from .cli_processor import ProcessingResult
from .performance_tracker import PerformanceTracker, BatchPerformanceTracker


class HybridProcessor:
    """
    Hybrid processor that downloads locally and uses Salad Cloud directly for transcription.

    This combines the benefits of:
    - Local YouTube download (avoiding remote API's yt-dlp issues)
    - Direct Salad Cloud transcription (bypassing Hugging Face API)
    - Local summarization (using OpenAI directly)
    """

    def __init__(self, config: Dict[str, Any], output_manager: OutputManager,
                 verbose: bool = False):
        """
        Initialize hybrid processor.

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

        # Initialize local components including Salad transcriber
        self._init_local_components()

        self.logger.info("Hybrid processor initialized with direct Salad Cloud transcription")

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for hybrid processing."""
        logger = logging.getLogger("hybrid_processor")

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

    def _init_local_components(self):
        """Initialize local downloader, Salad transcriber, and summarizer components."""
        # Initialize downloaders
        self.yt_downloader = YTDownloader(config=self.config["youtube"])
        self.rss_downloader = RSS_Feed_Downloader(config=self.config["rss_feed"])

        # Initialize Salad transcriber for direct cloud transcription
        self.transcriber = SaladTranscriber(config=self.config["salad"])

        # Initialize summarizer
        self.summarizer = OpenAI_Summarizer(config=self.config["openai"])

        self.logger.info("Initialized local components (downloaders + Salad transcriber + summarizer)")

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

    def _transcribe_with_salad(self, audio_path: str, video_id: str) -> str:
        """
        Transcribe audio file directly using Salad Cloud.

        This bypasses the Hugging Face API and uses Salad Cloud directly:
        1. Uploads audio to Salad Storage
        2. Submits transcription job to Salad
        3. Polls for completion and returns transcript

        Args:
            audio_path (str): Path to local audio file
            video_id (str): Video identifier

        Returns:
            str: Transcription text

        Raises:
            Exception: If transcription fails
        """
        self.logger.info(f"Transcribing with Salad Cloud (direct)...")

        try:
            # Use SaladTranscriber directly - it handles upload and transcription
            transcript = self.transcriber.transcribe(
                audio_path=audio_path,
                video_id=video_id
            )

            self.logger.info("Salad Cloud transcription completed successfully")
            return transcript

        except Exception as e:
            self.logger.error(f"Salad Cloud transcription failed: {e}")
            raise

    def process_single(self, source_url: str, platform: str,
                      options: Dict[str, Any]) -> ProcessingResult:
        """
        Process a single podcast episode using hybrid mode.

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
            processing_mode="hybrid",
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
                        metadata={"message": "Already processed (hybrid)"},
                        performance_tracker=perf_tracker
                    )

            self.logger.info(f"Starting hybrid processing: {source_url}")

            # Stage 2: Download locally
            perf_tracker.start_stage("local_download")
            downloader = self.yt_downloader if platform == "youtube" else self.rss_downloader

            self.logger.info("Downloading audio locally...")
            try:
                audio_path, metadata = downloader.download_episode(source_url, episode_name)
                metadata["source_url"] = source_url
                metadata["platform"] = platform
                metadata["processed_via"] = "hybrid"
                perf_tracker.stop_stage(
                    audio_path=audio_path,
                    title=metadata.get("title", "Unknown"),
                    duration=metadata.get("duration_string", "Unknown")
                )
            except Exception as e:
                perf_tracker.stop_stage(error=str(e))
                perf_tracker.stop_processing(success=False, error=f"Local download failed: {str(e)}")
                return ProcessingResult(
                    success=False,
                    error=f"Local download failed: {str(e)}",
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

            # Stage 3: Salad Cloud transcription (if requested)
            if options.get("transcribe", True) and not options.get("summarize_only", False):
                perf_tracker.start_stage("salad_transcription")
                self.logger.info("Transcribing with Salad Cloud...")
                try:
                    transcript = self._transcribe_with_salad(
                        audio_path=audio_path,
                        video_id=metadata.get("video_id", "unknown")
                    )
                    perf_tracker.stop_stage(
                        transcription_method="salad_cloud_direct",
                        transcript_length=len(transcript),
                        audio_duration=metadata.get("duration_string", "Unknown")
                    )
                    self.logger.info("Salad Cloud transcription completed")
                except Exception as e:
                    perf_tracker.stop_stage(error=str(e))
                    perf_tracker.stop_processing(success=False, error=f"Salad transcription failed: {str(e)}")
                    return ProcessingResult(
                        success=False,
                        error=f"Salad transcription failed: {str(e)}",
                        episode_path=episode_path,
                        metadata=metadata,
                        performance_tracker=perf_tracker
                    )

            # Stage 4: Local summarization (if requested and we have transcript)
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
                    perf_tracker.start_stage("local_summarization")
                    self.logger.info("Generating summary locally...")
                    try:
                        summary = self.summarizer.summarize(
                            transcript,
                            detail=options.get("detail_level", 0.5)
                        )
                        perf_tracker.stop_stage(
                            detail_level=options.get("detail_level", 0.5),
                            summary_length=len(summary),
                            transcript_length=len(transcript)
                        )
                        self.logger.info("Local summary generation completed")
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

            self.logger.info(f"Successfully processed episode (hybrid): {episode_path.name}")

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
            self.logger.exception(f"Unexpected error in hybrid processing: {source_url}")
            perf_tracker.stop_processing(success=False, error=f"Unexpected error: {str(e)}")
            return ProcessingResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                performance_tracker=perf_tracker
            )

    def process_batch(self, sources: List[Dict[str, str]],
                     options: Dict[str, Any]) -> List[ProcessingResult]:
        """
        Process multiple podcast episodes using hybrid mode.

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

        self.logger.info(f"Starting hybrid batch processing of {total} episodes")

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
        self.logger.info(f"Hybrid batch processing completed: {success_count}/{total} successful")

        # Print batch performance summary
        if self.verbose:
            batch_tracker.print_batch_summary()

        return results

    def get_component_info(self) -> Dict[str, str]:
        """Get information about hybrid processing components."""
        return {
            "processing_mode": "hybrid",
            "downloader": "local",
            "transcriber": "salad_cloud_direct",
            "summarizer": "local"
        }
