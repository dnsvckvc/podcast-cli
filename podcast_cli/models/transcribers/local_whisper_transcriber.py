import os
import logging
import whisper
from pathlib import Path
from .transcriber import Transcriber

logger = logging.getLogger(__name__)


class LocalWhisperTranscriber(Transcriber):
    """
    A class for transcribing audio files using OpenAI's Whisper model locally.
    
    This transcriber downloads and runs Whisper models on your local machine,
    requiring no API keys or internet connection after initial model download.
    """

    def __init__(self, config: dict):
        """
        Initialize the local Whisper transcriber.

        Args:
            config (dict): Configuration dictionary containing:
                - model (str): Whisper model size ("tiny", "base", "small", "medium", "large")
                - verbose (bool): Enable detailed logging
                - base_dir (str): Base directory for audio files
                - transcription_extension (str): File extension for transcripts
        """
        super().__init__(config)
        
        # Get model size from config (default to "base" for good balance of speed/accuracy)
        model_size = config.get("model", "base")
        
        if self.verbose:
            logger.info(f"Loading Whisper model: {model_size}")
        
        try:
            # Load the Whisper model (downloads on first use)
            self.model = whisper.load_model(model_size)
            if self.verbose:
                logger.info(f"Whisper model '{model_size}' loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model '{model_size}': {e}")
            raise RuntimeError(f"Could not initialize Whisper model: {e}")

    def transcribe(self, audio_path: str, video_id: str) -> str:
        """
        Transcribe audio file using local Whisper model.

        Args:
            audio_path (str): Path to the audio file to transcribe
            video_id (str): Unique identifier for the content

        Returns:
            str: The transcribed text
        """
        try:
            # Create base directory for this video
            base_dir = os.path.join(self.downloads_path, video_id)
            os.makedirs(base_dir, exist_ok=True)
            
            # Define transcript path
            transcript_path = os.path.join(
                base_dir, f"{video_id}{self.config.get('transcription_extension', '.txt')}"
            )
            
            # Check if transcript already exists
            if os.path.exists(transcript_path):
                if self.verbose:
                    logger.info(f"Loading existing transcript: {transcript_path}")
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            # Verify audio file exists
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            if self.verbose:
                logger.info(f"Transcribing audio file: {audio_path}")
            
            # Transcribe using local Whisper model
            result = self.model.transcribe(
                audio_path,
                verbose=self.verbose,
                word_timestamps=False  # Disable word-level timestamps for faster processing
            )
            
            # Extract text from result
            transcript_text = result["text"].strip()
            
            if not transcript_text:
                raise ValueError("Transcription resulted in empty text")
            
            # Save transcript to file
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)
            
            if self.verbose:
                logger.info(f"Transcript saved to: {transcript_path}")
                logger.info(f"Transcript length: {len(transcript_text)} characters")
            
            return transcript_text
            
        except Exception as e:
            logger.error(f"Transcription failed for {audio_path}: {e}")
            raise RuntimeError(f"Failed to transcribe audio: {e}")

    def get_model_info(self) -> dict:
        """Get information about the loaded Whisper model."""
        if hasattr(self, 'model'):
            return {
                "transcriber": "local_whisper",
                "model": self.config.get("model", "base"),
                "requires_api_key": False,
                "runs_locally": True
            }
        else:
            return {
                "transcriber": "local_whisper",
                "error": "Model not loaded"
            }