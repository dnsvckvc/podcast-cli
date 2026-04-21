import os
import json
import time
import logging
import requests

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from dotenv import load_dotenv
from .transcriber import Transcriber

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

        # Path to the most recent structured transcript JSON (full endpoint
        # only). HybridProcessor reads this after transcribe() returns so the
        # OutputManager can copy it next to transcript.txt.
        self.last_structured_path: Optional[str] = None

    def transcribe(self, audio_path: str, video_id: str) -> str:
        """
        Transcribe audio file or URL using Salad AI.

        Args:
            audio_path (str): Local file path or direct URL to audio
            video_id (str): Unique identifier for the content

        Returns:
            str: Transcribed text (plain text). When the full Salad endpoint is
            used, a structured JSON payload is also written next to the .txt
            file and exposed via ``self.last_structured_path``.
        """
        base_dir = os.path.join(self.downloads_path, video_id)
        os.makedirs(base_dir, exist_ok=True)

        transcript_path = os.path.join(
            base_dir, f"{video_id}{self.config.get('transcription_extension')}"
        )
        structured_path = os.path.join(base_dir, f"{video_id}.json")
        self.last_structured_path = None

        if os.path.exists(transcript_path):
            if self.verbose:
                logger.info("Transcript already exists, loading from file")
            if os.path.exists(structured_path):
                self.last_structured_path = structured_path
            with open(transcript_path, "r", encoding="utf-8") as f:
                return f.read()

        try:
            if audio_path.startswith(("http://", "https://")):
                if self.verbose:
                    logger.info(f"Transcribing from URL: {audio_path}")
                transcribed_text, structured = self.transcribe_from_url(audio_path)
            else:
                if self.verbose:
                    logger.info(f"Uploading and transcribing file: {audio_path}")
                transcript_url = self.upload(audio_path)
                transcribed_text, structured = self.transcribe_from_url(transcript_url)

            self.save_transcript(transcribed_text, transcript_path)

            if structured is not None:
                with open(structured_path, "w", encoding="utf-8") as f:
                    json.dump(structured, f, indent=2, ensure_ascii=False)
                self.last_structured_path = structured_path

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
                            self.config.get("signature_expiration", 14400)
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

    def _build_payload(self, file_url: str, use_lite: bool) -> Dict[str, Any]:
        """
        Build the Salad job payload.

        For the lite endpoint we only send ``url`` + ``return_as_file`` because
        lite ignores the rest. For the full endpoint we wire through
        language_code, sentence-level timestamps, and diarization (which
        requires sentence_diarization per the Salad docs).
        """
        salad_input: Dict[str, Any] = {
            "url": file_url,
            "return_as_file": False,
        }

        if not use_lite:
            language_code = self.config.get("language_code")
            if language_code:
                salad_input["language_code"] = language_code

            # Default sentence-level timestamps to True (matches Salad's own
            # default and is what the structured output is keyed off of).
            salad_input["sentence_level_timestamps"] = bool(
                self.config.get("sentence_level_timestamps", True)
            )

            diarization = bool(self.config.get("diarization", False))
            if diarization:
                salad_input["diarization"] = True
                # Per Salad docs, sentence-level speaker labels require
                # sentence_diarization to be explicitly enabled.
                salad_input["sentence_diarization"] = True

        return {"input": salad_input}

    def _fetch_remote_output(self, output_url: str) -> Dict[str, Any]:
        """Fetch the >1MB Salad result file referenced by ``output.url``."""
        if self.verbose:
            logger.info(f"Fetching large Salad result file: {output_url}")
        resp = requests.get(
            output_url, headers={"Salad-Api-Key": SALAD_API_KEY}, timeout=120
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_full_output(self, output: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Parse the full Salad endpoint output into (plain_text, structured_dict).

        The plain text is composed by joining the ``text`` of each
        sentence-level timestamp entry. The structured dict is what gets
        written to ``transcript.json`` next to ``transcript.txt``.
        """
        sentences = output.get("sentence_level_timestamps") or []

        plain_text_parts = []
        for sentence in sentences:
            text = (sentence.get("text") or "").strip()
            if text:
                plain_text_parts.append(text)
        plain_text = " ".join(plain_text_parts)

        structured = {
            "sentences": sentences,
            "duration": output.get("duration"),
            "processing_time": output.get("processing_time"),
        }
        return plain_text, structured

    def transcribe_from_url(self, file_url: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Submit a transcription job, poll for completion, and return the result.

        Returns:
            Tuple of (plain_text, structured_payload). ``structured_payload`` is
            ``None`` for the lite endpoint and a dict for the full endpoint.
        """
        use_lite = bool(self.config.get("use_lite", False))
        endpoint = "transcription-lite" if use_lite else "transcribe"
        payload = self._build_payload(file_url, use_lite)

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
                logger.info(
                    f"Transcription job submitted to '{endpoint}': {job_id}"
                )

            # Poll for completion. Defaults: 7s interval, 90 minute window —
            # generous enough for a 2.5h episode (Salad's hard upper bound)
            # transcribed with diarization on the full endpoint. Both knobs
            # are tunable via config.json under the "salad" block.
            poll_interval_s = int(self.config.get("poll_interval_s", 7))
            max_poll_minutes = int(self.config.get("max_poll_minutes", 90))
            max_attempts = max(1, (max_poll_minutes * 60) // poll_interval_s)
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
                            elapsed_min = (attempt * poll_interval_s) / 60
                            logger.info(
                                f"Job {job_id} status: {status} "
                                f"(elapsed {elapsed_min:.1f}m / {max_poll_minutes}m), waiting..."
                            )
                        time.sleep(poll_interval_s)
                        attempt += 1
                        continue

                    if status != "succeeded":
                        error_msg = job_status.get(
                            "error", f"Job failed with status: {status}"
                        )
                        raise Exception(f"Transcription job failed: {error_msg}")

                    output = job_status.get("output", {}) or {}
                    if output.get("error"):
                        logger.error("Transcription failed: " + output["error"])
                        raise ValueError("Transcription error: " + output["error"])

                    # Salad returns a downloadable file URL when the inline
                    # response would exceed 1MB; fetch and replace `output`.
                    if output.get("url") and not output.get("text") \
                            and not output.get("sentence_level_timestamps"):
                        output = self._fetch_remote_output(output["url"])

                    if use_lite:
                        return output.get("text", ""), None

                    return self._parse_full_output(output)

                except requests.RequestException as e:
                    logger.warning(f"Status check failed (attempt {attempt}): {e}")
                    if attempt >= max_attempts - 1:
                        raise
                    time.sleep(poll_interval_s)
                    attempt += 1

            raise Exception(
                f"Transcription job timed out after {max_poll_minutes} minutes "
                f"(job_id={job_id}). The job may still be running on Salad — "
                f"increase salad.max_poll_minutes in config.json and retry, "
                f"or query the job directly via the Salad API."
            )

        except requests.RequestException as e:
            logger.error(f"Transcription request failed: {e}")
            raise Exception(f"Transcription request failed")

    def _sign_file(self, fname: str, expires_s: int = 14400) -> str:
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
