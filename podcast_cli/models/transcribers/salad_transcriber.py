import os
import time
import logging
import requests

from pathlib import Path
from dotenv import load_dotenv
from models.transcribers.transcriber import Transcriber

load_dotenv(override=True)

logger = logging.getLogger(__name__)

SALAD_API_KEY = os.getenv("SALAD_API_KEY")
SALAD_ORGANIZATION = os.getenv("SALAD_ORGANIZATION")


class SaladTranscriber(Transcriber):
    """
    Salad AI transcription service integration.

    This transcriber handles both file uploads and direct URL transcription
    using Salad's cloud transcription service.
    """

    def __init__(self, config: dict):
        """
        Initialize the Salad transcriber.

        Args:
            config (dict): Configuration dictionary
        """
        super().__init__(config)

        if not SALAD_API_KEY:
            raise ValueError("SALAD_API_KEY environment variable is required")
        if not SALAD_ORGANIZATION:
            raise ValueError("SALAD_ORGANIZATION environment variable is required")

    def transcribe(self, audio_path: str, video_id: str) -> str:
        """
        Transcribe audio file or URL using Salad AI.

        Args:
            audio_path (str): Local file path or direct URL to audio
            video_id (str): Unique identifier for the content

        Returns:
            str: Transcribed text
        """
        base_dir = os.path.join(self.downloads_path, video_id)
        os.makedirs(base_dir, exist_ok=True)

        transcript_path = os.path.join(
            base_dir, f"{video_id}{self.config.get('transcription_extension')}"
        )

        if os.path.exists(transcript_path):
            if self.verbose:
                logger.info("Transcript already exists, loading from file")
            with open(transcript_path, "r", encoding="utf-8") as f:
                return f.read()

        try:
            if audio_path.startswith(("http://", "https://")):
                if self.verbose:
                    logger.info(f"Transcribing from URL: {audio_path}")
                transcribed_text = self.transcribe_from_url(audio_path)
            else:
                if self.verbose:
                    logger.info(f"Uploading and transcribing file: {audio_path}")
                transcript_url = self.upload(audio_path)
                transcribed_text = self.transcribe_from_url(transcript_url)

            self.save_transcript(transcribed_text, transcript_path)
            return transcribed_text

        except Exception as e:
            logger.error(f"Transcription failed for {video_id}: {e}")
            raise Exception(f"Transcription failed")

    def upload(self, audio_path: str) -> str:
        """
        Upload audio file to Salad storage.

        Args:
            audio_path (str): Path to local audio file

        Returns:
            str: URL of uploaded file
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size = Path(audio_path).stat().st_size
        max_direct_upload = self.config.get("max_direct_upload", 104857600)  # 100MB

        if file_size <= max_direct_upload:
            if self.verbose:
                logger.info(
                    f"Using direct upload for {audio_path} ({file_size / (1024*1024):.2f} MB)"
                )
            return self._simple_upload(audio_path)
        else:
            if self.verbose:
                logger.info(
                    f"Using multipart upload for {audio_path} ({file_size / (1024*1024):.2f} MB)"
                )
            return self._multipart_upload(audio_path)

    def _simple_upload(self, audio_path: str) -> str:
        """
        Upload file using simple PUT request.

        Args:
            audio_path (str): Path to audio file

        Returns:
            str: Signed URL for the uploaded file
        """
        fname = Path(audio_path).name

        try:
            with open(audio_path, "rb") as file_data:
                response = requests.put(
                    f"{self.config.get('storage_base_url')}/{SALAD_ORGANIZATION}/files/{fname}",
                    headers={"Salad-Api-Key": SALAD_API_KEY},
                    files={"file": (fname, file_data, "audio/mpeg")},
                    data={
                        "mimeType": "audio/mpeg",
                        "sign": "true",
                        "signatureExp": str(
                            self.config.get("signature_expiration", 259200)
                        ),
                    },
                )
                response.raise_for_status()

            result = response.json()
            return result.get("url")

        except requests.RequestException as e:
            logger.error(f"Simple upload failed: {e}")
            raise Exception(f"File upload failed")

    def _multipart_upload(self, audio_path: str) -> str:
        """
        Upload large file using multipart upload.

        Args:
            audio_path (str): Path to audio file

        Returns:
            str: URL of uploaded file
        """
        fname = Path(audio_path).name
        file_size_bytes = Path(audio_path).stat().st_size
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        if self.verbose:
            logger.info(f"Size of audio file is {file_size_mb} MB")

        try:
            init_response = requests.put(
                f"{self.config.get('storage_base_url')}/{SALAD_ORGANIZATION}/files/{fname}?action=mpu-create",
                headers={"Salad-Api-Key": SALAD_API_KEY},
            )
            init_response.raise_for_status()
            upload_id = init_response.json()["uploadId"]

            if self.verbose:
                logger.info(f"Upload id is: {upload_id}")

            etags = []
            chunk_size = self.config.get("max_direct_upload", 104857600)

            with open(audio_path, "rb") as f:
                part_num = 1
                while chunk := f.read(chunk_size):
                    chunk_size_mb = round(len(chunk) / (1024 * 1024), 2)
                    if self.verbose:
                        logger.info(
                            f"Uploading chunk #{part_num} of size {chunk_size_mb} MB"
                        )
                    part_response = requests.put(
                        f"{self.config.get('storage_base_url')}/{SALAD_ORGANIZATION}/file_parts/{fname}?partNumber={part_num}&uploadId={upload_id}",
                        headers={
                            "Salad-Api-Key": SALAD_API_KEY,
                            "Content-Type": "application/octet-stream",
                        },
                        data=chunk,
                    )
                    part_response.raise_for_status()

                    if self.verbose:
                        logger.info(f"Uploaded chunk #{part_num}")

                    etags.append(
                        {"partNumber": part_num, "etag": part_response.json()["etag"]}
                    )
                    part_num += 1

            # 3. Complete multipart upload
            complete_response = requests.put(
                f"{self.config.get('storage_base_url')}/{SALAD_ORGANIZATION}/files/{fname}?action=mpu-complete&uploadId={upload_id}",
                headers={
                    "Salad-Api-Key": SALAD_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"parts": etags},
            )
            complete_response.raise_for_status()
            # For multipart upload, we need to sign the filename, not the returned URL
            return self._sign_file(fname)

        except requests.RequestException as e:
            logger.error(f"Multipart upload failed: {e}")
            raise Exception(f"Multipart upload failed")

    def transcribe_from_url(self, file_url: str) -> str:
        """
        Submit transcription job and poll for completion.

        Args:
            file_url (str): URL of audio file to transcribe

        Returns:
            str: Transcribed text
        """
        payload = {
            "input": {
                "url": file_url,
                "return_as_file": False,
            }
        }

        # Choose endpoint based on configuration
        endpoint = "transcription-lite" if self.config.get("use_lite", True) else "transcribe"
        
        try:
            response = requests.post(
                f"{self.config.get('transcript_base_url')}/{SALAD_ORGANIZATION}/inference-endpoints/{endpoint}/jobs",
                headers={
                    "Salad-Api-Key": SALAD_API_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            job_id = response.json()["id"]

            if self.verbose:
                logger.info(f"Transcription job submitted: {job_id}")

            # Poll for completion
            max_attempts = 120  # 14 minutes max (120 * 7 seconds)
            attempt = 0

            while attempt < max_attempts:
                try:
                    status_response = requests.get(
                        f"{self.config.get('transcript_base_url')}/{SALAD_ORGANIZATION}/inference-endpoints/{endpoint}/jobs/{job_id}",
                        headers={"Salad-Api-Key": SALAD_API_KEY},
                    )
                    status_response.raise_for_status()

                    job_status = status_response.json()
                    status = job_status.get("status")

                    if status in ("created", "pending", "started", "running"):
                        if self.verbose:
                            logger.info(f"Job {job_id} status: {status}, waiting...")
                        time.sleep(7)
                        attempt += 1
                        continue
                    elif status == "succeeded":
                        if job_status.get("output", {}).get("error"):
                            logger.error(
                                "Transcription failed: " + job_status["output"]["error"]
                            )
                            raise ValueError(
                                "Transcription error: " + job_status["output"]["error"]
                            )
                        return job_status.get("output", {}).get("text", "")
                    else:
                        error_msg = job_status.get(
                            "error", f"Job failed with status: {status}"
                        )
                        raise Exception(f"Transcription job failed: {error_msg}")

                except requests.RequestException as e:
                    logger.warning(f"Status check failed (attempt {attempt}): {e}")
                    if attempt >= max_attempts - 1:
                        raise
                    time.sleep(7)
                    attempt += 1

            raise Exception("Transcription job timed out")

        except requests.RequestException as e:
            logger.error(f"Transcription request failed: {e}")
            raise Exception(f"Transcription request failed")

    def _sign_file(self, fname: str, expires_s: int = 3600) -> str:
        """
        Sign a file URL for access.

        Args:
            fname (str): File name
            expires_s (int): Expiration time in seconds

        Returns:
            str: Signed URL
        """
        try:
            resp = requests.post(
                f"{self.config.get('storage_base_url')}/{SALAD_ORGANIZATION}/file_tokens/{fname}",
                headers={"Salad-Api-Key": SALAD_API_KEY},
                json={"method": "GET", "exp": expires_s},
            )
            resp.raise_for_status()
            return resp.json()["url"]
        except requests.RequestException as e:
            logger.error(f"File signing failed: {e}")
            raise Exception(f"Failed to sign file")
