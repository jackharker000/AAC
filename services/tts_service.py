import io
from typing import Optional
from config import get_settings

settings = get_settings()


async def synthesize_speech(text: str, voice_id: Optional[str] = None) -> bytes:
    """
    Convert text to speech using ElevenLabs.
    Returns raw MP3 bytes. Raises on failure so the caller can fall back to browser TTS.
    """
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not configured")

    from elevenlabs.client import ElevenLabs

    vid = voice_id or settings.elevenlabs_voice_id
    if not vid:
        raise RuntimeError("ELEVENLABS_VOICE_ID not configured")

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    audio_generator = client.generate(
        text=text,
        voice=vid,
        model=settings.elevenlabs_model,
    )

    # Consume the generator into bytes
    chunks = []
    for chunk in audio_generator:
        if isinstance(chunk, bytes):
            chunks.append(chunk)
    return b"".join(chunks)


async def list_voices() -> dict:
    """Return available ElevenLabs voices for the settings screen."""
    if not settings.elevenlabs_api_key:
        return {"voices": []}

    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    response = client.voices.get_all()
    voices = [
        {"voice_id": v.voice_id, "name": v.name, "category": getattr(v, "category", "")}
        for v in response.voices
    ]
    return {"voices": voices}
