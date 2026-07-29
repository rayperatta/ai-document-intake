"""Application configuration via environment variables.

All settings are read through pydantic-settings so they can be overridden
with environment variables or a .env file. No real API keys are ever
hardcoded — the mock provider is the default.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────
    llm_provider: str = "mock"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite:///./docintake.db"

    # ── API ──────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Notification ─────────────────────────────────────────
    notify_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
