from typing import Optional
from config import get_settings

settings = get_settings()

# Cached auto-selected voice ID (used when ELEVENLABS_VOICE_ID is not set)
_auto_voice_id: Optional[str] = None


def elevenlabs_available() -> bool:
    return bool(settings.elevenlabs_api_key)


async def _resolve_voice_id(override: Optional[str] = None) -> str:
    """Return the voice ID to use, auto-selecting the first available if none configured."""
    global _auto_voice_id

    vid = override or settings.elevenlabs_voice_id
    if vid:
        return vid

    # Auto-select: fetch first voice from the account
    if _auto_voice_id:
        return _auto_voice_id

    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    response = client.voices.get_all()
    if response.voices:
        _auto_voice_id = response.voices[0].voice_id
        return _auto_voice_id

    raise RuntimeError("No ElevenLabs voices found on this account")


async def synthesize_speech(text: str, voice_id: Optional[str] = None) -> bytes:
    """
    Convert text to speech using ElevenLabs.
    Returns raw MP3 bytes. Raises on failure so the caller falls back to browser TTS.
    """
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ElevenLabs not configured — using browser TTS")

    from elevenlabs.client import ElevenLabs

    vid = await _resolve_voice_id(voice_id)
    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    audio_generator = client.generate(
        text=text,
        voice=vid,
        model=settings.elevenlabs_model,
    )

    chunks = [chunk for chunk in audio_generator if isinstance(chunk, bytes)]
    return b"".join(chunks)


async def list_voices() -> dict:
    """Return available ElevenLabs voices for the settings screen."""
    if not settings.elevenlabs_api_key:
        return {"voices": []}

    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    response = client.voices.get_all()
    return {
        "voices": [
            {"voice_id": v.voice_id, "name": v.name, "category": getattr(v, "category", "")}
            for v in response.voices
        ]
    }
