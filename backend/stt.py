"""Google Cloud Speech-to-Text module for STAT."""

import json
import os

from google.cloud import speech
from google.oauth2 import service_account


def _get_stt_client() -> speech.SpeechClient:
    """Create a Speech-to-Text client from environment credentials."""
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS_JSON is not set")

    info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(info)
    return speech.SpeechClient(credentials=credentials)


def transcribe(audio_bytes: bytes) -> str:
    """Transcribe WebM/Opus audio bytes to text using Google Cloud STT.

    Args:
        audio_bytes: Raw audio file content (WebM format).

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError: If transcription fails or returns no results.
    """
    client = _get_stt_client()

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        sample_rate_hertz=48000,
        language_code="zh-TW",
    )

    response = client.recognize(config=config, audio=audio)

    if not response.results:
        raise RuntimeError("語音辨識未回傳任何結果")

    transcript = "".join(
        result.alternatives[0].transcript for result in response.results
    )

    if not transcript.strip():
        raise RuntimeError("語音辨識結果為空")

    return transcript.strip()
