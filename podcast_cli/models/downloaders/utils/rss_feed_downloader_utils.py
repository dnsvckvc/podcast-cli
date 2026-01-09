import re
import logging
import requests
import feedparser

from datetime import datetime
from typing import Tuple, Any, Optional, Dict

logger = logging.getLogger(__name__)


def get_episode_entry(
    source_url: str, episode_name: str
) -> Tuple[Optional[Any], Optional[str]]:
    """
    Retrieve an episode entry from the RSS feed by matching the title.

    Args:
        source_url (str): The URL of the RSS feed
        episode_name (str): The title of the desired episode

    Returns:
        Tuple[Optional[Any], Optional[str]]: Episode entry and channel name,
        or (None, None) if not found
    """
    try:
        response = requests.get(
            source_url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; PodcastSummarizer/1.0)"},
        )
        response.raise_for_status()

        feed = feedparser.parse(response.content)
        channel_name = feed.get("feed", {}).get("title", "Unknown Podcast")

        normalized_target = _normalize_title(episode_name)

        for entry in feed.entries:
            normalized_entry = _normalize_title(entry.title)

            if normalized_target == normalized_entry:
                return entry, channel_name

            if normalized_target in normalized_entry:
                return entry, channel_name

        return None, None

    except Exception as e:
        logger.error(f"Error fetching RSS feed: {e}")
        raise requests.RequestException("Failed to fetch RSS feed")


def generate_episode_id(audio_url: str, title: str) -> str:
    """
    Generate a unique episode ID from URL or title.

    Args:
        audio_url (str): The audio file URL
        title (str): The episode title

    Returns:
        str: Generated episode ID
    """
    url_parts = audio_url.split("/")
    for part in reversed(url_parts):
        if part and not part.startswith("?"):
            clean_part = part.split(".")[0].split("?")[0]
            if clean_part and len(clean_part) > 3:
                return clean_part

    normalized_title = re.sub(r"[^\w\s]", "", title.lower())
    return "_".join(normalized_title.split()[:5])


def get_metadata(entry: Any) -> Dict[str, Any]:
    """
    Extract metadata from a feed entry.

    Args:
        entry: An RSS feed entry object

    Returns:
        Dict[str, Any]: Metadata dictionary with episode information
    """

    raw_duration = entry.get("itunes_duration")
    duration_string = None

    if raw_duration:
        if raw_duration.isdigit():
            duration_string = _format_duration(int(raw_duration))
        else:
            duration_string = raw_duration

    published_parsed = entry.get("published_parsed")
    if published_parsed:
        try:
            dt = datetime(*published_parsed[:6])
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_str = "Unknown"
    else:
        date_str = "Unknown"

    thumbnail = None
    if hasattr(entry, "image") and entry.image:
        thumbnail = entry.image.get("href")
    elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        thumbnail = entry.media_thumbnail[0].get("url")

    return {
        "title": entry.get("title", "Unknown Episode"),
        "thumbnail": thumbnail,
        "duration_string": duration_string,
        "release_date": date_str,
        "author": entry.get("author", ""),
    }


def _format_duration(seconds: int) -> str:
    """
    Convert duration in seconds to formatted string.

    Args:
        seconds (int): Duration in seconds

    Returns:
        str: Formatted duration as "HH:MM:SS" or "MM:SS"
    """
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


def _normalize_title(title: str) -> str:
    """
    Normalize title for comparison by removing special characters and converting to lowercase.

    Args:
        title (str): The title to normalize

    Returns:
        str: Normalized title
    """
    if not title:
        return ""

    normalized = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(normalized.split())
