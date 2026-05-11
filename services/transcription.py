import io
from typing import Optional
from openai import AsyncOpenAI
from config import get_settings

settings = get_settings()
_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """
    Send audio bytes to OpenAI Whisper and return the transcribed text.
    Browser MediaRecorder produces WebM/Opus which Whisper accepts natively.
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    client = _get_client()
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "audio.webm"

    response = await client.audio.transcriptions.create(
        model=settings.whisper_model,
        file=audio_file,
        language="en",
        response_format="text",
    )
    return response.strip() if isinstance(response, str) else response.text.strip()
