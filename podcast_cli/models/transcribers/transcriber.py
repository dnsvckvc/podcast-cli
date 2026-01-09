import os
import logging

from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Transcriber(ABC):
    """
    Abstract base class for audio transcription services.

    This class defines the interface that all transcribers must implement
    to ensure consistent behavior across different transcription services.
    """

    def __init__(self, config: dict):
        """
        Initialize the transcriber with configuration settings.

        Args:
            config (dict): Configuration dictionary containing:
                - verbose (bool): Enable detailed logging
                - base_dir (str): Base directory for temporary files
                - downloads_dir (str): Subdirectory for audio files
                - transcription_extension (str): File extension for transcripts
        """
        self.config = config
        self.verbose = config.get("verbose")
        self.downloads_path = os.path.join(
            self.config.get("base_dir"), self.config.get("downloads_dir")
        )

        # Ensure downloads directory exists
        os.makedirs(self.downloads_path, exist_ok=True)

    def save_transcript(self, transcribed_text: str, transcript_path: str) -> None:
        """
        Save the transcribed text to a file.

        Args:
            transcribed_text (str): The transcribed text content
            transcript_path (str): Path where the transcript will be saved
        """
        try:
            os.makedirs(os.path.dirname(transcript_path), exist_ok=True)

            with open(transcript_path, "w", encoding="utf-8") as file:
                file.write(transcribed_text)

            if self.verbose:
                logger.info(f"Transcript saved at: {transcript_path}")

        except Exception as e:
            logger.error(f"Failed to save transcript to {transcript_path}: {e}")
            raise Exception(f"Failed to save transcript")

    @abstractmethod
    def transcribe(self, audio_path: str, video_id: str) -> str:
        """
        Transcribe the audio file at the given path or URL.

        Args:
            audio_path (str): Path to local audio file or URL to audio content
            video_id (str): Unique identifier for the content

        Returns:
            str: The transcribed text

        Raises:
            Exception: If transcription fails
        """
        pass
