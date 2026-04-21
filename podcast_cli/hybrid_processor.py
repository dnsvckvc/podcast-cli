import os
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from pathlib import Path

from .models.downloaders.yt_downloader import YTDownloader
from .models.downloaders.rss_feed_downloader import RSS_Feed_Downloader
from .models.transcribers.salad_transcriber import SaladTranscriber
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


class HybridProcessor:
    """
    Hybrid processor: download locally, transcribe via Salad Cloud directly.

    Pipeline:
      - Local YouTube/RSS download (avoids upstream yt-dlp issues in remote APIs)
      - Direct Salad Cloud transcription (lite or full endpoint, selected by config)
    """

    def __init__(self, config: Dict[str, Any], output_manager: OutputManager,
                 verbose: bool = False):
        self.config = config
        self.output_manager = output_manager
        self.verbose = verbose

        self.logger = self._setup_logger()
        self._init_local_components()

        self.logger.info("Hybrid processor initialized (Salad Cloud transcription)")

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for hybrid processing."""
        logger = logging.getLogger("hybrid_processor")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)

        return logger

    def _init_local_components(self):
        """Initialize local downloaders and the Salad transcriber."""
        self.yt_downloader = YTDownloader(config=self.config["youtube"])
        self.rss_downloader = RSS_Feed_Downloader(config=self.config["rss_feed"])
        self.transcriber = SaladTranscriber(config=self.config["salad"])

        self.logger.info("Initialized local downloaders + Salad transcriber")

    def validate_input(self, source_url: str, platform: str,
                       episode_name: Optional[str] = None) -> Dict[str, Any]:
        """Validate input parameters before processing."""
        platform_validation = InputValidator.validate_platform(platform)
        if not platform_validation["valid"]:
            return platform_validation

        platform = platform_validation["value"]

        if platform == "youtube":
            url_validation = URLValidator.validate_youtube_url(source_url)
        else:
            url_validation = URLValidator.validate_rss_url(source_url)

        if not url_validation["valid"]:
            return url_validation

        if platform == "rss":
            episode_validation = InputValidator.validate_episode_name(episode_name, platform)
            if not episode_validation["valid"]:
                return episode_validation
            episode_name = episode_validation["value"]

        return {
            "valid": True,
            "platform": platform,
            "source_url": source_url,
            "episode_name": episode_name,
        }

    def _transcribe_with_salad(self, audio_path: str, video_id: str) -> str:
        """Transcribe a local audio file via Salad Cloud."""
        self.logger.info("Transcribing with Salad Cloud...")
        try:
            transcript = self.transcriber.transcribe(audio_path=audio_path, video_id=video_id)
            self.logger.info("Salad Cloud transcription completed")
            return transcript
        except Exception as e:
            self.logger.error(f"Salad Cloud transcription failed: {e}")
            raise

    def process_single(self, source_url: str, platform: str,
                       options: Dict[str, Any]) -> ProcessingResult:
        """Process a single podcast episode."""
        episode_id = f"{platform}_{hash(source_url) % 1000000}"
        perf_tracker = PerformanceTracker(
            episode_id=episode_id,
            processing_mode="hybrid",
            verbose=self.verbose,
        )
        perf_tracker.start_processing()

        try:
            # Stage 1: Validation
            perf_tracker.start_stage("validation")
            validation = self.validate_input(
                source_url, platform, options.get("episode_name")
            )
            if not validation["valid"]:
                perf_tracker.stop_stage(error=validation.get("error"))
                perf_tracker.stop_processing(success=False, error="Validation failed")
                return ProcessingResult(
                    success=False,
                    error=f"Validation failed: {validation.get('error', 'Unknown error')}",
                    performance_tracker=perf_tracker,
                )
            perf_tracker.stop_stage()

            episode_name = validation.get("episode_name")

            # Dedupe
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
                        performance_tracker=perf_tracker,
                    )

            self.logger.info(f"Starting hybrid processing: {source_url}")

            # Stage 2: Local download
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
                    duration=metadata.get("duration_string", "Unknown"),
                )
            except Exception as e:
                perf_tracker.stop_stage(error=str(e))
                perf_tracker.stop_processing(success=False, error=f"Local download failed: {str(e)}")
                return ProcessingResult(
                    success=False,
                    error=f"Local download failed: {str(e)}",
                    performance_tracker=perf_tracker,
                )

            episode_path = self.output_manager.create_episode_folder(
                source_url, metadata, platform
            )

            perf_tracker.performance.episode_metadata = metadata

            # Stage 3: Salad Cloud transcription
            perf_tracker.start_stage("salad_transcription")
            try:
                transcript = self._transcribe_with_salad(
                    audio_path=audio_path,
                    video_id=metadata.get("video_id", "unknown"),
                )
                perf_tracker.stop_stage(
                    transcription_method=(
                        "salad_lite" if self.config["salad"].get("use_lite", False)
                        else "salad_full"
                    ),
                    transcript_length=len(transcript),
                    audio_duration=metadata.get("duration_string", "Unknown"),
                )
            except Exception as e:
                perf_tracker.stop_stage(error=str(e))
                perf_tracker.stop_processing(success=False, error=f"Salad transcription failed: {str(e)}")
                return ProcessingResult(
                    success=False,
                    error=f"Salad transcription failed: {str(e)}",
                    episode_path=episode_path,
                    metadata=metadata,
                    performance_tracker=perf_tracker,
                )

            # Stage 4: Save files
            perf_tracker.start_stage("file_operations")
            structured_path = getattr(self.transcriber, "last_structured_path", None)
            files_created = self.output_manager.save_episode_files(
                episode_path=episode_path,
                audio_path=audio_path,
                transcript=transcript,
                metadata=metadata,
                processing_options=options,
                structured_transcript_path=structured_path,
            )

            if audio_path and "/tmp/" in audio_path:
                temp_dir = os.path.dirname(audio_path)
                self.output_manager.cleanup_temp_files(temp_dir)

            perf_tracker.stop_stage(
                files_created=len(files_created),
                output_path=str(episode_path),
            )

            perf_tracker.stop_processing(success=True)
            perf_tracker.save_performance_data(episode_path)

            self.logger.info(f"Successfully processed episode: {episode_path.name}")

            if self.verbose:
                perf_tracker.print_performance_report()

            return ProcessingResult(
                success=True,
                episode_path=episode_path,
                metadata=metadata,
                files_created=files_created,
                performance_tracker=perf_tracker,
            )

        except Exception as e:
            self.logger.exception(f"Unexpected error in hybrid processing: {source_url}")
            perf_tracker.stop_processing(success=False, error=f"Unexpected error: {str(e)}")
            return ProcessingResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                performance_tracker=perf_tracker,
            )

    def process_batch(self, sources: List[Dict[str, str]],
                      options: Dict[str, Any]) -> List[ProcessingResult]:
        """Process multiple podcast episodes."""
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
                options={**options, "episode_name": source.get("episode_name")},
            )

            results.append(result)

            if result.performance_tracker:
                batch_tracker.add_episode_performance(result.performance_tracker.performance)

            if result.success:
                self.logger.info(
                    f"Success: {result.episode_path.name if result.episode_path else 'Unknown'}"
                )
            else:
                self.logger.error(f"Failed: {result.error}")

        batch_tracker.stop_batch()

        success_count = sum(1 for r in results if r.success)
        self.logger.info(f"Hybrid batch processing completed: {success_count}/{total} successful")

        if self.verbose:
            batch_tracker.print_batch_summary()

        return results

    def get_component_info(self) -> Dict[str, str]:
        """Information about hybrid processing components."""
        return {
            "processing_mode": "hybrid",
            "downloader": "local",
            "transcriber": (
                "salad_lite" if self.config["salad"].get("use_lite", False)
                else "salad_full"
            ),
        }
