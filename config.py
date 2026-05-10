from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    database_url: str = "sqlite+aiosqlite:///./aac.db"
    app_port: int = 8000
    app_host: str = "127.0.0.1"

    # Prompt generation settings
    claude_model: str = "claude-sonnet-4-6"
    max_prompt_suggestions: int = 5
    context_max_tokens: int = 1500
    transcript_context_turns: int = 10
    memory_context_limit: int = 8

    # Audio / transcription
    whisper_model: str = "whisper-1"
    audio_chunk_seconds: int = 3

    # TTS
    elevenlabs_model: str = "eleven_turbo_v2"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
