import os
import json
import time
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import re


class OutputManager:
    """
    Manages structured output directories and file operations for CLI processing.
    
    Creates organized folder structure:
    output_path/
    ├── youtube_VIDEOID/
    │   ├── metadata.json
    │   ├── audio.mp3
    │   ├── transcript.txt
    │   └── transcript.json   (only when Salad full endpoint is used)
    ├── rss_EPISODESLUG/
    │   ├── metadata.json
    │   ├── audio.mp3
    │   ├── transcript.txt
    │   └── transcript.json
    └── .cli_cache/
        └── processing_log.json
    """

    def __init__(self, base_output_path: str):
        """
        Initialize output manager with base output directory.
        
        Args:
            base_output_path (str): Base directory for all output
        """
        self.base_path = Path(base_output_path).resolve()
        self.cache_path = self.base_path / ".cli_cache"
        self.processing_log_path = self.cache_path / "processing_log.json"
        
        # Create base directories
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.cache_path.mkdir(exist_ok=True)
        
        # Initialize processing log
        self._init_processing_log()

    def _init_processing_log(self):
        """Initialize or load existing processing log."""
        if not self.processing_log_path.exists():
            self._save_processing_log({
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "processed_episodes": {}
            })

    def _load_processing_log(self) -> Dict[str, Any]:
        """Load processing log from cache."""
        if self.processing_log_path.exists():
            with open(self.processing_log_path, 'r') as f:
                return json.load(f)
        return {"processed_episodes": {}}

    def _save_processing_log(self, log_data: Dict[str, Any]):
        """Save processing log to cache."""
        with open(self.processing_log_path, 'w') as f:
            json.dump(log_data, f, indent=2)

    def _sanitize_filename(self, name: str, max_length: int = 50) -> str:
        """
        Sanitize filename by replacing special characters and limiting length.
        
        Args:
            name (str): Original filename
            max_length (int): Maximum filename length
            
        Returns:
            str: Sanitized filename
        """
        # Replace special characters with underscores
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Replace spaces with underscores
        sanitized = re.sub(r'\s+', '_', sanitized)
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Strip leading/trailing underscores
        sanitized = sanitized.strip('_')
        # Limit length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip('_')
        
        return sanitized or "unknown"

    def create_episode_folder(self, source_url: str, metadata: Dict[str, Any], platform: str) -> Path:
        """
        Create episode-specific folder and return path.
        
        Args:
            source_url (str): Source URL of the content
            metadata (Dict[str, Any]): Episode metadata
            platform (str): Platform type ('youtube' or 'rss')
            
        Returns:
            Path: Path to created episode folder
        """
        if platform == "youtube":
            # Extract video ID from URL or metadata
            video_id = self._extract_youtube_video_id(source_url)
            if not video_id:
                video_id = metadata.get("video_id", "unknown")
            folder_name = f"youtube_{video_id}"
        else:  # rss
            # Use episode title or provided name
            episode_name = metadata.get("title", "unknown_episode")
            sanitized_name = self._sanitize_filename(episode_name)
            # Get release date and format as YYYY_MM_DD prefix
            release_date = metadata.get("release_date")
            if release_date:
                try:
                    # Parse various date formats and convert to YYYY_MM_DD
                    if "T" in release_date:
                        date_part = release_date.split("T")[0]
                    else:
                        date_part = release_date
                    # Replace any separators with underscores
                    date_prefix = date_part.replace("-", "_").replace("/", "_")
                except:
                    date_prefix = time.strftime("%Y_%m_%d")  # fallback to current date
            else:
                date_prefix = time.strftime("%Y_%m_%d")  # fallback to current date
            folder_name = f"{date_prefix}_{sanitized_name}"
        
        episode_path = self.base_path / folder_name
        episode_path.mkdir(exist_ok=True)
        
        return episode_path

    def _extract_youtube_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        patterns = [
            r'youtube\.com/watch\?v=([^&]+)',
            r'youtu\.be/([^?]+)',
            r'youtube\.com/embed/([^?]+)',
            r'youtube\.com/v/([^?]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def save_episode_files(self, episode_path: Path, audio_path: str, transcript: str,
                          metadata: Dict[str, Any],
                          processing_options: Dict[str, Any],
                          structured_transcript_path: Optional[str] = None) -> Dict[str, Path]:
        """
        Save all episode files to the episode directory.

        Args:
            episode_path (Path): Episode directory path
            audio_path (str): Path to downloaded audio file
            transcript (str): Transcribed text
            metadata (Dict[str, Any]): Episode metadata
            processing_options (Dict[str, Any]): Processing configuration used
            structured_transcript_path (Optional[str]): Path to a structured
                transcript JSON (sentence/diarization data) produced by the
                Salad full endpoint, if any. Will be copied next to transcript.txt.

        Returns:
            Dict[str, Path]: Paths to saved files
        """
        saved_files = {}

        enhanced_metadata = {
            **metadata,
            "processing_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cli_version": "1.0.0",
            "processing_options": processing_options
        }

        metadata_path = episode_path / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(enhanced_metadata, f, indent=2)
        saved_files["metadata"] = metadata_path

        if audio_path and os.path.exists(audio_path):
            audio_dest = episode_path / "audio.mp3"
            if Path(audio_path).resolve() != audio_dest.resolve():
                shutil.copy2(audio_path, audio_dest)
            saved_files["audio"] = audio_dest

        if transcript:
            transcript_path = episode_path / "transcript.txt"
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            saved_files["transcript"] = transcript_path

        if structured_transcript_path and os.path.exists(structured_transcript_path):
            structured_dest = episode_path / "transcript.json"
            if Path(structured_transcript_path).resolve() != structured_dest.resolve():
                shutil.copy2(structured_transcript_path, structured_dest)
            saved_files["transcript_structured"] = structured_dest

        self._log_processed_episode(str(episode_path.name), enhanced_metadata)

        return saved_files

    def _log_processed_episode(self, episode_folder: str, metadata: Dict[str, Any]):
        """Log processed episode to processing log."""
        log_data = self._load_processing_log()
        log_data["processed_episodes"][episode_folder] = {
            "title": metadata.get("title", "Unknown"),
            "processed_at": metadata.get("processing_timestamp"),
            "source_url": metadata.get("source_url"),
            "platform": metadata.get("platform")
        }
        log_data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self._save_processing_log(log_data)

    def is_already_processed(self, source_url: str, platform: str, 
                           episode_name: Optional[str] = None) -> Optional[Path]:
        """
        Check if episode was already processed and return its path if exists.
        
        Args:
            source_url (str): Source URL
            platform (str): Platform type
            episode_name (Optional[str]): Episode name for RSS feeds
            
        Returns:
            Optional[Path]: Path to existing episode folder if found
        """
        log_data = self._load_processing_log()
        
        for folder_name, episode_data in log_data["processed_episodes"].items():
            if platform == "youtube":
                # For YouTube, check the source URL directly
                if episode_data.get("source_url") == source_url:
                    folder_path = self.base_path / folder_name
                    if folder_path.exists():
                        return folder_path
            elif platform == "rss":
                # For RSS feeds, we need to check the specific episode
                # First check if it's the same RSS feed
                if episode_data.get("source_url") == source_url:
                    # Then check if it's the same episode by comparing titles
                    stored_title = episode_data.get("title", "")
                    if episode_name and stored_title:
                        # Normalize both titles for comparison
                        from podcast_cli.models.downloaders.utils.rss_feed_downloader_utils import _normalize_title
                        if _normalize_title(stored_title) == _normalize_title(episode_name):
                            folder_path = self.base_path / folder_name
                            if folder_path.exists():
                                return folder_path
                    # Also check by audio URL if available
                    episode_audio_url = episode_data.get("audio_url")
                    if episode_audio_url:
                        # Try to get the audio URL for the requested episode
                        try:
                            from podcast_cli.models.downloaders.utils.rss_feed_downloader_utils import get_episode_entry
                            entry, _ = get_episode_entry(source_url, episode_name)
                            if entry and hasattr(entry, "enclosures") and entry.enclosures:
                                for enclosure in entry.enclosures:
                                    if "audio" in enclosure.get("type", "").lower():
                                        if episode_audio_url == enclosure.href:
                                            folder_path = self.base_path / folder_name
                                            if folder_path.exists():
                                                return folder_path
                                        break
                        except:
                            # If we can't fetch the episode info, skip the audio URL check
                            pass
        
        return None

    def get_processing_stats(self) -> Dict[str, Any]:
        """Get statistics about processed episodes."""
        log_data = self._load_processing_log()
        episodes = log_data.get("processed_episodes", {})
        
        platforms = {}
        for episode_data in episodes.values():
            platform = episode_data.get("platform", "unknown")
            platforms[platform] = platforms.get(platform, 0) + 1
        
        return {
            "total_episodes": len(episodes),
            "platforms": platforms,
            "output_directory": str(self.base_path),
            "cache_directory": str(self.cache_path)
        }

    def cleanup_temp_files(self, temp_dir: str):
        """Clean up temporary files after processing."""
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                # Log but don't fail on cleanup errors
                pass