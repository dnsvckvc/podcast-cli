import re
import os
import json
import shutil
import logging

from typing import Tuple, Optional
from yt_dlp import YoutubeDL
from models.downloaders.downloader import Downloader
from models.downloaders.utils.yt_downloader_utils import extract_video_id, load_metadata

logger = logging.getLogger(__name__)


class YTDownloader(Downloader):
    """
    YouTube downloader for podcast content.

    This class handles downloading YouTube videos as audio files,
    extracting metadata, and preparing them for transcription.
    """

    def __init__(self, config: dict):
        """
        Initialize the YouTube downloader.

        Args:
            config (dict): Configuration dictionary containing:
                - verbose (bool): Enable detailed logging
                - base_dir (str): Base directory for downloads
                - downloads_dir (str): Subdirectory for audio files
                - file_ext (str): Audio file extension
                - metadata_ext (str): Metadata file extension
                - cookies_path (str): Path to YouTube cookies file
        """
        self.config = config
        self.verbose = config.get("verbose")
        self.downloads_path = os.path.join(
            config.get("base_dir"), config.get("downloads_dir")
        )

        # Ensure downloads directory exists
        os.makedirs(self.downloads_path, exist_ok=True)

    def validate_url(self, url: str) -> bool:
        """
        Validate if the URL is a valid YouTube URL.

        Args:
            url (str): The YouTube URL to validate

        Returns:
            bool: True if valid YouTube URL, False otherwise
        """
        if not url or not isinstance(url, str):
            return False

        youtube_patterns = [
            r"^https?://(www\.)?youtube\.com/watch\?v=[\w-]+",
            r"^https?://(www\.)?youtu\.be/[\w-]+",
            r"^https?://(www\.)?youtube\.com/embed/[\w-]+",
            r"^https?://(www\.)?youtube\.com/v/[\w-]+",
            r"^https?://m\.youtube\.com/watch\?v=[\w-]+",
        ]

        for pattern in youtube_patterns:
            if re.match(pattern, url):
                video_id = extract_video_id(url)
                return video_id is not None and len(video_id) == 11

        return False

    def download_episode(
        self, source_url: str, episode_name: Optional[str]
    ) -> Tuple[str, dict]:
        """
        Download YouTube video as audio and extract metadata.

        Args:
            source_url (str): YouTube video URL
            episode_name (Optional[str]): Not used for YouTube (title from metadata)

        Returns:
            Tuple[str, dict]: Local audio file path and metadata

        Raises:
            ValueError: If URL is invalid
            Exception: For download-related errors
        """
        if not self.validate_url(source_url):
            raise ValueError("Invalid YouTube URL provided")

        self.source_url = source_url.split("&")[0]
        self.video_id = extract_video_id(self.source_url)

        if not self.video_id:
            raise ValueError("Could not extract video ID from URL")

        try:
            mp3_path = self._download_file(
                self.config.get("file_ext", ".mp3"), audio_only=True
            )

            # Download metadata
            metadata_path = self._download_file(
                self.config.get("metadata_ext", ".info.json")
            )

            # Load and process metadata
            metadata = load_metadata(metadata_path)
            metadata["video_id"] = self.video_id
            metadata["source_type"] = "youtube"

            if self.verbose:
                logger.info(
                    f"Successfully downloaded YouTube video: {metadata.get('title', 'Unknown')}"
                )

            return mp3_path, metadata

        except Exception as e:
            logger.error(f"Error downloading YouTube video {self.video_id}: {e}")
            raise Exception(f"Failed to download YouTube video")

    def _download_file(self, extension: str, audio_only: bool = False) -> str:
        """
        Download file using yt-dlp.

        Args:
            extension (str): File extension
            audio_only (bool): Whether to download audio only

        Returns:
            str: Path to downloaded file
        """
        outdir = os.path.join(self.downloads_path, self.video_id)
        os.makedirs(outdir, exist_ok=True)

        output_template = os.path.join(outdir, f"{self.video_id}{extension}")

        opts = {
            "ffmpeg_location": shutil.which("ffmpeg"),
            "outtmpl": os.path.join(self.downloads_path, "%(id)s", "%(id)s.%(ext)s"),
            "no_cache_dir": True,
            "cache_dir": None,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }

        # Add Node.js path for JavaScript runtime (if available)
        node_path = shutil.which("node")
        if node_path:
            opts["exec_cmd"] = {"node": node_path}

        if cookiefile := self.config.get("cookies_path"):
            if os.path.exists(cookiefile):
                opts["cookiefile"] = cookiefile
            elif self.verbose:
                logger.warning(f"Cookies file not found: {cookiefile}")

        if audio_only:
            opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": extension.strip("."),
                            "preferredquality": "192",
                        }
                    ],
                }
            )
        else:
            opts.update({"skip_download": True, "writeinfojson": True})

        if self.verbose and audio_only:
            logger.info(
                f"Downloading with yt-dlp options: {json.dumps(opts, indent=2)}"
            )

        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([self.source_url])
        except Exception as e:
            logger.error(f"yt-dlp download failed: {e}")
            raise

        return output_template
