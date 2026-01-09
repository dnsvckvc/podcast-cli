import json
import logging

from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats.

    Args:
        url (str): YouTube URL

    Returns:
        Optional[str]: Video ID if found, None otherwise
    """
    try:
        parsed_url = urlparse(url)

        if parsed_url.hostname in [
            "www.youtube.com",
            "youtube.com",
            "m.youtube.com",
        ]:
            if parsed_url.path == "/watch":
                query_params = parse_qs(parsed_url.query)
                return query_params.get("v", [None])[0]
            elif parsed_url.path.startswith("/embed/"):
                return parsed_url.path.split("/embed/")[1].split("?")[0]
            elif parsed_url.path.startswith("/v/"):
                return parsed_url.path.split("/v/")[1].split("?")[0]

        elif parsed_url.hostname in ["youtu.be"]:
            return parsed_url.path[1:].split("?")[0]

    except Exception as e:
        logger.warning(f"Error extracting video ID: {e}")

    return None


def load_metadata(metadata_path: str) -> dict:
    """
    Load and process metadata from JSON file.

    Args:
        metadata_path (str): Path to metadata file

    Returns:
        dict: Processed metadata
    """
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        metadata = {
            "title": raw_data.get("title", "Unknown Title"),
            "channel": raw_data.get(
                "uploader", raw_data.get("channel", "Unknown Channel")
            ),
            "duration_string": _format_duration(raw_data.get("duration", 0)),
            "release_date": _format_date(raw_data.get("upload_date")),
            "thumbnail": raw_data.get("thumbnail"),
        }

        return metadata

    except Exception as e:
        logger.error(f"Failed to load metadata from {metadata_path}: {e}")
        return {
            "title": "Unknown Title",
            "channel": "Unknown Channel",
            "duration_string": "Unknown",
            "release_date": "Unknown",
            "thumbnail": None,
        }


def _format_duration(seconds: Optional[int]) -> str:
    """
    Format duration from seconds to HH:MM:SS or MM:SS.

    Args:
        seconds (Optional[int]): Duration in seconds

    Returns:
        str: Formatted duration
    """
    if not seconds or not isinstance(seconds, (int, float)):
        return "Unknown"

    try:
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "Unknown"


def _format_date(date_str: Optional[str]) -> str:
    """
    Format upload date from YYYYMMDD to YYYY-MM-DD.

    Args:
        date_str (Optional[str]): Date string in YYYYMMDD format

    Returns:
        str: Formatted date or "Unknown"
    """
    if not date_str or not isinstance(date_str, str) or len(date_str) != 8:
        return "Unknown"

    try:
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"
    except (ValueError, IndexError):
        return "Unknown"
