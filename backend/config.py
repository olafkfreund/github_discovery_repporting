from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    DATABASE_URL: str = "postgresql+asyncpg://devops:devops@localhost:5432/devops_discovery"
    ANTHROPIC_API_KEY: str = ""
    CREDENTIALS_ENCRYPTION_KEY: str = ""
    REPORTS_DIR: str = "./reports"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    MAX_CONCURRENT_SCANS: int = 3
    MAX_CONCURRENT_REPORTS: int = 5
    MAX_CONCURRENT_AGENT_RUNS: int = 2
    AGENT_FEATURE_ENABLED: bool = True
    SCAN_ENRICHMENT_MAX_FINDINGS: int = 50
    SCAN_ENRICHMENT_MAX_TOKENS_PER_SCAN: int = 50_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
