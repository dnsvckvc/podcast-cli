import re
import requests
import feedparser

from urllib.parse import urlparse
from typing import Dict, Any, Optional


class URLValidator:
    """
    Utility class for validating different types of URLs.
    """

    @staticmethod
    def validate_youtube_url(url: str) -> Dict[str, Any]:
        """
        Validate YouTube URL and extract video information.

        Args:
            url (str): YouTube URL to validate

        Returns:
            Dict[str, Any]: Validation result with 'valid' boolean and optional 'video_id'
        """
        if not url or not isinstance(url, str):
            return {"valid": False, "error": "URL is required and must be a string"}

        youtube_patterns = [
            r"^https?://(www\.)?youtube\.com/watch\?v=[\w-]+",
            r"^https?://(www\.)?youtu\.be/[\w-]+",
            r"^https?://(www\.)?youtube\.com/embed/[\w-]+",
            r"^https?://(www\.)?youtube\.com/v/[\w-]+",
            r"^https?://m\.youtube\.com/watch\?v=[\w-]+",
        ]

        for pattern in youtube_patterns:
            if re.match(pattern, url):
                video_id = URLValidator._extract_youtube_video_id(url)
                if video_id and len(video_id) == 11:
                    return {"valid": True, "video_id": video_id, "platform": "youtube"}

        return {"valid": False, "error": "Invalid YouTube URL format or video ID"}

    @staticmethod
    def validate_rss_url(url: str, timeout: int = 10) -> Dict[str, Any]:
        """
        Validate RSS feed URL and check if it contains podcast episodes.

        Args:
            url (str): RSS feed URL to validate
            timeout (int): Request timeout in seconds

        Returns:
            Dict[str, Any]: Validation result with 'valid' boolean and optional metadata
        """
        if not url or not isinstance(url, str):
            return {"valid": False, "error": "URL is required and must be a string"}

        try:
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return {"valid": False, "error": "Invalid URL format"}

            if parsed.scheme not in ["http", "https"]:
                return {"valid": False, "error": "URL must use HTTP or HTTPS protocol"}

        except Exception:
            return {"valid": False, "error": "Invalid URL format"}

        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; PodcastSummarizer/1.0)",
                    "Accept": "application/rss+xml, application/xml, text/xml",
                },
            )
            response.raise_for_status()

            feed = feedparser.parse(response.content)

            if not hasattr(feed, "entries"):
                return {"valid": False, "error": "Invalid RSS feed format"}

            if len(feed.entries) == 0:
                return {"valid": False, "error": "RSS feed contains no episodes"}

            feed_info = feed.get("feed", {})
            if not feed_info.get("title"):
                return {"valid": False, "error": "RSS feed missing title"}

            audio_episodes = []
            for entry in feed.entries[:10]:
                if hasattr(entry, "enclosures") and entry.enclosures:
                    for enclosure in entry.enclosures:
                        if "audio" in enclosure.get("type", "").lower():
                            audio_episodes.append(
                                {
                                    "title": entry.get("title", "Unknown"),
                                    "published": entry.get("published", "Unknown"),
                                }
                            )
                            break

            if not audio_episodes:
                return {"valid": False, "error": "No audio episodes found in RSS feed"}

            return {
                "valid": True,
                "platform": "rss",
                "feed_title": feed_info.get("title", "Unknown Podcast"),
                "episode_count": len(feed.entries),
                "audio_episodes": len(audio_episodes),
                "sample_episodes": audio_episodes[:5],
            }

        except requests.Timeout:
            return {
                "valid": False,
                "error": "Request timed out - RSS feed may be slow or unavailable",
            }
        except requests.RequestException as e:
            return {"valid": False, "error": f"Failed to fetch RSS feed: {str(e)}"}
        except Exception as e:
            return {"valid": False, "error": f"Error parsing RSS feed: {str(e)}"}

    @staticmethod
    def _extract_youtube_video_id(url: str) -> Optional[str]:
        """
        Extract YouTube video ID from various URL formats.

        Args:
            url (str): YouTube URL

        Returns:
            Optional[str]: Video ID if found, None otherwise
        """
        try:
            from urllib.parse import parse_qs

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

        except Exception:
            pass

        return None


class InputValidator:
    """
    Utility class for validating input parameters.
    """

    @staticmethod
    def validate_detail_level(detail_level: Any) -> Dict[str, Any]:
        """
        Validate detail level parameter.

        Args:
            detail_level: Detail level value to validate

        Returns:
            Dict[str, Any]: Validation result
        """
        if detail_level is None:
            return {"valid": True, "value": 0.5}

        try:
            detail_float = float(detail_level)
            if 0.0 <= detail_float <= 1.0:
                return {"valid": True, "value": detail_float}
            else:
                return {
                    "valid": False,
                    "error": "Detail level must be between 0.0 and 1.0",
                }
        except (ValueError, TypeError):
            return {
                "valid": False,
                "error": "Detail level must be a number between 0.0 and 1.0",
            }

    @staticmethod
    def validate_episode_name(episode_name: Any, platform: str) -> Dict[str, Any]:
        """
        Validate episode name parameter.

        Args:
            episode_name: Episode name to validate
            platform (str): Platform type ('youtube' or 'rss')

        Returns:
            Dict[str, Any]: Validation result
        """
        if platform == "rss":
            if not episode_name or not isinstance(episode_name, str):
                return {
                    "valid": False,
                    "error": "Episode name is required for RSS feeds",
                }
            if len(episode_name.strip()) < 3:
                return {
                    "valid": False,
                    "error": "Episode name must be at least 3 characters long",
                }
            return {"valid": True, "value": episode_name.strip()}
        else:
            return {"valid": True, "value": episode_name}

    @staticmethod
    def validate_platform(platform: Any) -> Dict[str, Any]:
        """
        Validate platform parameter.

        Args:
            platform: Platform value to validate

        Returns:
            Dict[str, Any]: Validation result
        """
        if not platform or not isinstance(platform, str):
            return {"valid": False, "error": "Platform is required"}

        if platform.lower() in ["youtube", "rss"]:
            return {"valid": True, "value": platform.lower()}
        else:
            return {
                "valid": False,
                "error": "Platform must be either 'youtube' or 'rss'",
            }
