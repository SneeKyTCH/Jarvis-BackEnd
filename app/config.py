"""
Configuration management for JARVIS Backend
Loads settings from environment variables using Pydantic v2
"""

from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # ─── Server Configuration ───
    environment: str = "development"
    debug: bool = True
    api_port: int = 8000
    api_host: str = "0.0.0.0"
    api_title: str = "JARVIS Backend API v2.0"
    api_description: str = "Production-grade universal AI assistant"
    api_version: str = "2.0.0"

    # ─── Database ───
    database_url: str = "postgresql://jarvis:jarvis@localhost:5432/jarvis_db"
    database_url_async: str = "postgresql+asyncpg://jarvis:jarvis@localhost:5432/jarvis_db"
    sqlite_url: str = "sqlite:///./jarvis.db"
    use_sqlite_fallback: bool = True  # Use SQLite if PostgreSQL unavailable

    # ─── Redis Cache ───
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True

    # ─── AI/LLM APIs ───
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    preferred_model: str = "claude"  # "claude" or "openai"

    # ─── Voice & Audio ───
    elevenlabs_api_key: str = ""
    google_speech_api_key: str = ""
    default_voice_id: str = "George"  # Eleven Labs voice
    speech_recognition_language: str = "ro"  # Default: Romanian

    # ─── Web Search ───
    tavily_api_key: str = ""
    duckduckgo_search_enabled: bool = True
    search_cache_ttl_hours: int = 24

    # ─── Security ───
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ─── CORS ───
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "https://jarvis-web-dun-five.vercel.app",
        "https://*.vercel.app",
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]

    # ─── Logging ───
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "text"

    # ─── AWS S3 (Optional) ───
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket_name: str = "jarvis-voice-cache"
    voice_cache_ttl_days: int = 45

    # ─── Voice Processing ───
    max_audio_file_size_mb: int = 25
    supported_audio_formats: List[str] = ["wav", "mp3", "ogg", "flac"]
    speech_recognition_timeout_seconds: int = 30

    # ─── API Rate Limiting ───
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # ─── Conversation Limits ───
    max_messages_per_conversation: int = 10000
    max_conversation_context_tokens: int = 8000
    conversation_retention_days: int = 90

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export for easy import
settings = get_settings()
