import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
import json


@dataclass
class StageTimer:
    """Timer for individual processing stages."""
    name: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

    def start(self):
        """Start the timer."""
        self.start_time = time.time()
        return self

    def stop(self, **metadata):
        """Stop the timer and record metadata."""
        if self.start_time is None:
            raise ValueError("Timer was not started")
        
        self.end_time = time.time()  
        self.duration = self.end_time - self.start_time
        self.metadata = metadata or {}
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "duration_seconds": round(self.duration, 3) if self.duration else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metadata": self.metadata or {}
        }


@dataclass 
class ProcessingPerformance:
    """Complete performance metrics for episode processing."""
    episode_id: str
    processing_mode: str  # "local" or "remote"
    total_duration: Optional[float] = None
    stages: Optional[List[StageTimer]] = None
    episode_metadata: Optional[Dict[str, Any]] = None
    system_info: Optional[Dict[str, str]] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.stages is None:
            self.stages = []
        if self.timestamp is None:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "episode_id": self.episode_id,
            "processing_mode": self.processing_mode,
            "total_duration_seconds": round(self.total_duration, 3) if self.total_duration else None,
            "timestamp": self.timestamp,
            "stages": [stage.to_dict() for stage in self.stages],
            "episode_metadata": self.episode_metadata or {},
            "system_info": self.system_info or {}
        }


class PerformanceTracker:
    """
    Tracks processing performance across different stages and episodes.
    
    Provides timing for downloads, transcription, summarization, and overall processing.
    """

    def __init__(self, episode_id: str, processing_mode: str, verbose: bool = False):
        """
        Initialize performance tracker.
        
        Args:
            episode_id (str): Unique identifier for the episode
            processing_mode (str): "local" or "remote"
            verbose (bool): Enable verbose logging
        """
        self.episode_id = episode_id
        self.processing_mode = processing_mode
        self.verbose = verbose
        self.logger = logging.getLogger("performance_tracker")
        
        # Performance data
        self.performance = ProcessingPerformance(
            episode_id=episode_id,
            processing_mode=processing_mode
        )
        
        # Timing state
        self.start_time = None
        self.current_stage = None
        
        # Collect system info
        self._collect_system_info()

    def _collect_system_info(self):
        """Collect basic system information."""
        import platform
        import psutil
        
        try:
            self.performance.system_info = {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "python_version": platform.python_version(),
                "cpu_count": psutil.cpu_count(),
                "memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
                "processing_mode": self.processing_mode
            }
        except Exception as e:
            self.logger.warning(f"Could not collect system info: {e}")
            self.performance.system_info = {"processing_mode": self.processing_mode}

    def start_processing(self, episode_metadata: Dict[str, Any] = None):
        """Start overall processing timer."""
        self.start_time = time.time()
        self.performance.episode_metadata = episode_metadata or {}
        
        if self.verbose:
            self.logger.info(f"🚀 Started processing episode: {self.episode_id}")

    def start_stage(self, stage_name: str) -> StageTimer:
        """Start timing a processing stage."""
        # Stop current stage if active
        if self.current_stage and not self.current_stage.end_time:
            self.current_stage.stop()
        
        # Start new stage
        stage = StageTimer(name=stage_name).start()
        self.current_stage = stage
        self.performance.stages.append(stage)
        
        if self.verbose:
            self.logger.info(f"⏱️  Started stage: {stage_name}")
        
        return stage

    def stop_stage(self, **metadata):
        """Stop current stage with optional metadata."""
        if self.current_stage and not self.current_stage.end_time:
            self.current_stage.stop(**metadata)
            
            if self.verbose:
                duration = self.current_stage.duration
                self.logger.info(f"✅ Completed stage: {self.current_stage.name} ({duration:.2f}s)")

    def stop_processing(self, success: bool = True, error: str = None):
        """Stop overall processing timer."""
        # Stop current stage if active
        if self.current_stage and not self.current_stage.end_time:
            self.current_stage.stop()
        
        # Calculate total duration
        if self.start_time:
            self.performance.total_duration = time.time() - self.start_time
        
        # Add final metadata
        final_metadata = {
            "success": success,
            "error": error if error else None
        }
        
        if success and self.verbose:
            total_time = self.performance.total_duration
            self.logger.info(f"🎉 Processing completed in {total_time:.2f}s")
        elif not success and self.verbose:
            self.logger.info(f"❌ Processing failed: {error}")

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get human-readable performance summary."""
        if not self.performance.stages:
            return {"status": "no_timing_data"}
        
        summary = {
            "episode_id": self.episode_id,
            "processing_mode": self.processing_mode,
            "total_time": f"{self.performance.total_duration:.2f}s" if self.performance.total_duration else "unknown",
            "stages": {}
        }
        
        # Stage breakdown
        for stage in self.performance.stages:
            if stage.duration:
                summary["stages"][stage.name] = f"{stage.duration:.2f}s"
        
        # Performance insights
        if self.performance.total_duration and self.performance.episode_metadata:
            duration_str = self.performance.episode_metadata.get("duration_string", "")
            if duration_str:
                # Try to extract duration for performance ratio
                try:
                    # Parse duration like "01:05:34" or "45:22"
                    parts = duration_str.split(":")
                    if len(parts) == 3:  # HH:MM:SS
                        episode_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    elif len(parts) == 2:  # MM:SS
                        episode_seconds = int(parts[0]) * 60 + int(parts[1])
                    else:
                        episode_seconds = None
                    
                    if episode_seconds:
                        ratio = self.performance.total_duration / episode_seconds
                        summary["performance_ratio"] = f"{ratio:.2f}x" 
                        summary["episode_duration"] = duration_str
                except:
                    pass
        
        return summary

    def save_performance_data(self, output_path: Path):
        """Save detailed performance data to file."""
        performance_file = output_path / "performance.json"
        
        try:
            with open(performance_file, 'w') as f:
                json.dump(self.performance.to_dict(), f, indent=2)
            
            if self.verbose:
                self.logger.info(f"📊 Performance data saved to {performance_file}")
                
        except Exception as e:
            self.logger.warning(f"Failed to save performance data: {e}")

    def print_performance_report(self):
        """Print a formatted performance report to console."""
        if not self.performance.stages:
            print("No performance data available")
            return
        
        print(f"\n{'='*60}")
        print(f"PERFORMANCE REPORT - {self.episode_id}")
        print(f"{'='*60}")
        print(f"Processing Mode: {self.processing_mode}")
        
        if self.performance.total_duration:
            print(f"Total Time: {self.performance.total_duration:.2f}s")
        
        print(f"\nStage Breakdown:")
        print(f"{'-'*40}")
        
        for stage in self.performance.stages:
            if stage.duration:
                percentage = (stage.duration / self.performance.total_duration * 100) if self.performance.total_duration else 0
                print(f"  {stage.name:<20} {stage.duration:>8.2f}s ({percentage:>5.1f}%)")
        
        # Episode info
        if self.performance.episode_metadata:
            metadata = self.performance.episode_metadata
            print(f"\nEpisode Info:")
            print(f"{'-'*40}")
            if metadata.get("title"):
                print(f"  Title: {metadata['title'][:50]}...")
            if metadata.get("duration_string"):
                print(f"  Duration: {metadata['duration_string']}")
            if metadata.get("channel"):
                print(f"  Channel: {metadata['channel']}")
        
        # System info
        if self.performance.system_info:
            sys_info = self.performance.system_info
            print(f"\nSystem Info:")
            print(f"{'-'*40}")
            if sys_info.get("cpu_count"):
                print(f"  CPU Cores: {sys_info['cpu_count']}")
            if sys_info.get("memory_gb"):
                print(f"  RAM: {sys_info['memory_gb']}GB")
            if sys_info.get("platform"):
                print(f"  Platform: {sys_info['platform']}")
        
        print(f"{'='*60}\n")


class BatchPerformanceTracker:
    """Tracks performance across multiple episodes in batch processing."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = logging.getLogger("batch_performance")
        self.episode_performances: List[ProcessingPerformance] = []
        self.batch_start_time = None
        self.batch_end_time = None

    def start_batch(self):
        """Start batch processing timer."""
        self.batch_start_time = time.time()
        if self.verbose:
            self.logger.info("🚀 Started batch processing")

    def add_episode_performance(self, performance: ProcessingPerformance):
        """Add episode performance data."""
        self.episode_performances.append(performance)

    def stop_batch(self):
        """Stop batch processing timer."""
        self.batch_end_time = time.time()
        if self.verbose:
            batch_duration = self.batch_end_time - self.batch_start_time
            self.logger.info(f"🎉 Batch processing completed in {batch_duration:.2f}s")

    def print_batch_summary(self):
        """Print batch processing summary."""
        if not self.episode_performances:
            print("No episode performance data available")
            return
            
        total_episodes = len(self.episode_performances)
        successful = sum(1 for ep in self.episode_performances if ep.total_duration)
        batch_duration = (self.batch_end_time - self.batch_start_time) if self.batch_end_time and self.batch_start_time else 0
        
        print(f"\n{'='*60}")
        print(f"BATCH PERFORMANCE SUMMARY")
        print(f"{'='*60}")
        print(f"Total Episodes: {total_episodes}")
        print(f"Successful: {successful}")
        print(f"Failed: {total_episodes - successful}")
        print(f"Batch Duration: {batch_duration:.2f}s")
        
        if successful > 0:
            avg_time_per_episode = sum(ep.total_duration for ep in self.episode_performances if ep.total_duration) / successful
            print(f"Average Time per Episode: {avg_time_per_episode:.2f}s")
            
            # Processing mode breakdown
            modes = {}
            for ep in self.episode_performances:
                mode = ep.processing_mode
                modes[mode] = modes.get(mode, 0) + 1
            
            print(f"\nProcessing Modes:")
            for mode, count in modes.items():
                print(f"  {mode}: {count} episodes")
        
        print(f"{'='*60}\n")