"""OpenAI Whisper Speech-to-Text module for STAT."""

import os

from openai import OpenAI


def transcribe(audio_bytes: bytes) -> str:
    """Transcribe WebM/Opus audio bytes to text using OpenAI Whisper.

    Args:
        audio_bytes: Raw audio file content (WebM format).

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError: If transcription fails or returns no results.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    response = client.audio.transcriptions.create(
        model="whisper-1",
        file=("recording.webm", audio_bytes),
        language="zh",
    )

    transcript = response.text.strip()
    if not transcript:
        raise RuntimeError("語音辨識結果為空")

    return transcript
