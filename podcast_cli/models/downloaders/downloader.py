from typing import Tuple, Optional, Union
from abc import ABC, abstractmethod


class Downloader(ABC):
    """
    Abstract base class for podcast downloaders.

    This class defines the interface that all downloaders must implement
    to ensure consistent behavior across different podcast sources.
    """

    @abstractmethod
    def download_episode(
        self, source_url: str, episode_name: Optional[str]
    ) -> Tuple[str, dict]:
        """
        Download a podcast episode from the given source.

        Args:
            source_url (str): The URL of the podcast source
            episode_name (Optional[str]): Name of the specific episode (if applicable)

        Returns:
            Tuple[str, dict]: A tuple containing the local file path and metadata

        Raises:
            ValueError: If the source URL is invalid or episode not found
            Exception: For other download-related errors
        """
        pass

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """
        Validate if the provided URL is supported by this downloader.

        Args:
            url (str): The URL to validate

        Returns:
            bool: True if URL is valid and supported, False otherwise
        """
        pass
