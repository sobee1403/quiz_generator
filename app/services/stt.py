"""
파이프라인 내 STT: 음성 파일 → 전사 JSON (segments).
"""

from pathlib import Path
from typing import Any

from openai import OpenAI

from app.core.config import settings


def transcribe(audio_path: Path) -> dict[str, Any]:
    """
    음성 파일을 OpenAI 전사 API로 변환해 segments 포함 JSON 반환.
    """
    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.REQUEST_TIMEOUT,
    )
    with audio_path.open("rb") as f:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe-diarize",
            file=f,
            response_format="diarized_json",
            chunking_strategy="auto",
        )
    if not hasattr(transcript, "segments"):
        raise ValueError("API response missing 'segments'")
    segments = getattr(transcript, "segments", []) or []
    duration = getattr(transcript, "duration", None)
    return {
        "segments": [
            {
                "text": getattr(s, "text", ""),
                "start": getattr(s, "start", 0.0),
                "end": getattr(s, "end", 0.0),
                "speaker": getattr(s, "speaker", None),
            }
            for s in segments
        ],
        "duration": duration,
    }
