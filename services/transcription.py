import io
from typing import Optional
from openai import AsyncOpenAI
from config import get_settings

settings = get_settings()
_client: Optional[AsyncOpenAI] = None

# Maps MIME type (possibly with codecs suffix) to a filename extension Whisper accepts
_MIME_TO_EXT = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/wave": "wav",
    "audio/flac": "flac",
    "audio/x-m4a": "m4a",
}


def _ext_from_mime(mime_type: str) -> str:
    """Return a Whisper-compatible file extension for the given MIME type."""
    base = mime_type.split(";")[0].strip().lower()
    return _MIME_TO_EXT.get(base, "webm")


def _ext_from_magic(audio_bytes: bytes) -> str:
    """Detect audio format from file magic bytes as a fallback."""
    if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if audio_bytes[4:8] in (b"ftyp", b"moov", b"mdat"):
        return "mp4"
    if audio_bytes[:4] == b"OggS":
        return "ogg"
    if audio_bytes[:4] == b"RIFF":
        return "wav"
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    return "mp4"  # safe default for Safari


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "") -> str:
    """Send audio bytes to OpenAI Whisper and return the transcribed text."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    if mime_type:
        ext = _ext_from_mime(mime_type)
    else:
        ext = _ext_from_magic(audio_bytes)

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = f"audio.{ext}"

    client = _get_client()
    response = await client.audio.transcriptions.create(
        model=settings.whisper_model,
        file=audio_file,
        language="en",
        response_format="text",
    )
    return response.strip() if isinstance(response, str) else response.text.strip()
