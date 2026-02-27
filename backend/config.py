from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    DATABASE_URL: str = (
        "postgresql+asyncpg://devops:devops@localhost:5432/devops_discovery"
    )
    ANTHROPIC_API_KEY: str = ""
    CREDENTIALS_ENCRYPTION_KEY: str = ""
    REPORTS_DIR: str = "./reports"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
