"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe env parsing.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — all values sourced from .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # API Keys
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./vaaksetu.db"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # WebSocket
    ws_heartbeat_interval: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
