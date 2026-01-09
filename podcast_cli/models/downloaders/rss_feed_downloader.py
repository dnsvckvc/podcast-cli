import os
import json
import logging
import requests
import feedparser

from typing import Tuple, Optional
from urllib.parse import urlparse
from models.downloaders.downloader import Downloader
from models.downloaders.utils.rss_feed_downloader_utils import (
    get_metadata,
    get_episode_entry,
    generate_episode_id,
)

logger = logging.getLogger(__name__)


class RSS_Feed_Downloader(Downloader):
    """
    A class for handling podcast episodes from RSS feeds.

    This downloader validates RSS feeds and extracts episode metadata
    without downloading the actual audio files, as they will be processed
    directly from their URLs by the transcription service.
    """

    def __init__(self, config: dict):
        """
        Initialize the RSS Feed Downloader.

        Args:
            config (dict): Configuration dictionary containing:
                - verbose (bool): Enable detailed logging
                - base_dir (str): Base directory for temporary files
                - downloads_dir (str): Subdirectory for downloads
                - file_ext (str): File extension for audio files
                - chunk_size (int): Download chunk size in bytes
        """
        self.config = config
        self.verbose = config.get("verbose", False)
        self.downloads_path = os.path.join(
            config.get("base_dir"), config.get("downloads_dir")
        )

        os.makedirs(self.downloads_path, exist_ok=True)

    def validate_url(self, url: str) -> bool:
        """
        Validate if the URL is a valid RSS feed.

        Args:
            url (str): The RSS feed URL to validate

        Returns:
            bool: True if valid RSS feed, False otherwise
        """
        if not url or not isinstance(url, str):
            return False

        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            return False

        if parsed.scheme not in ["http", "https"]:
            return False

        try:
            response = requests.get(url)
            response.raise_for_status()

            feed = feedparser.parse(response.content)

            if not hasattr(feed, "entries") or len(feed.entries) == 0:
                return False
        except Exception as e:
            logger.warning(f"RSS feed validation failed: {e}")
            return False

        return True

    def download_episode(
        self, source_url: str, episode_name: Optional[str]
    ) -> Tuple[str, dict]:
        """
        Process a podcast episode from RSS feed.

        This method downloads the actual audio file to a local path
        for transcription processing.

        Args:
            source_url (str): URL of the RSS feed
            episode_name (Optional[str]): Name of the episode to process

        Returns:
            Tuple[str, dict]: A tuple containing:
                - audio_path (str): Local path to the downloaded audio file
                - metadata (dict): Episode metadata

        Raises:
            ValueError: If episode not found or invalid feed
            requests.RequestException: If feed cannot be fetched
        """
        if self.verbose:
            logger.info(f"Source URL is: {source_url}")
            logger.info(f"Episode name is: {episode_name}")

        if not self.validate_url(source_url):
            raise ValueError("Invalid RSS feed URL provided")

        if not episode_name:
            raise ValueError("Episode name is required for RSS feeds")

        entry, channel_name = get_episode_entry(source_url, episode_name)

        if not entry:
            raise ValueError(f"Episode '{episode_name}' not found in the RSS feed")

        if not hasattr(entry, "enclosures") or not entry.enclosures:
            raise ValueError("No audio enclosure found for this episode")

        audio_url = None
        for enclosure in entry.enclosures:
            if "audio" in enclosure.get("type", "").lower():
                audio_url = enclosure.href
                break

        if not audio_url:
            raise ValueError("No valid audio enclosure found")

        episode_id = generate_episode_id(audio_url, entry.title)

        metadata = get_metadata(entry)
        metadata["video_id"] = episode_id
        metadata["channel"] = channel_name
        metadata["audio_url"] = audio_url
        metadata["source_type"] = "rss"

        # Download the audio file to local storage
        local_audio_path = self._download_audio_file(audio_url, episode_id)

        if self.verbose:
            logger.info(
                f"Successfully processed RSS episode: {json.dumps(metadata, indent=4)}"
            )

        return local_audio_path, metadata

    def _download_audio_file(self, audio_url: str, episode_id: str) -> str:
        """
        Download audio file from URL to local storage.
        
        Args:
            audio_url (str): URL of the audio file
            episode_id (str): Unique identifier for the episode
            
        Returns:
            str: Local path to the downloaded audio file
        """
        import tempfile
        import urllib.parse
        
        # Create a temporary directory for this episode
        episode_dir = os.path.join(tempfile.gettempdir(), "audio", episode_id)
        os.makedirs(episode_dir, exist_ok=True)
        
        # Determine file extension from URL or default to mp3
        parsed_url = urllib.parse.urlparse(audio_url)
        file_ext = os.path.splitext(parsed_url.path)[1] or '.mp3'
        
        local_path = os.path.join(episode_dir, f"{episode_id}{file_ext}")
        
        # Check if file already exists
        if os.path.exists(local_path):
            if self.verbose:
                logger.info(f"Audio file already exists: {local_path}")
            return local_path
        
        if self.verbose:
            logger.info(f"Downloading audio from: {audio_url}")
        
        # Download the file
        try:
            chunk_size = self.config.get("chunk_size", 8192)
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
            
            if self.verbose:
                file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
                logger.info(f"Downloaded audio file: {local_path} ({file_size_mb:.2f} MB)")
                
            return local_path
            
        except Exception as e:
            # Clean up partial download
            if os.path.exists(local_path):
                os.remove(local_path)
            raise requests.RequestException(f"Failed to download audio file: {e}")
