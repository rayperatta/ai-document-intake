"""Smoke tests — verify the package imports and basic config works."""

from docintake import __version__
from docintake.config import get_settings


def test_version():
    assert __version__ == "0.1.0"


def test_settings_defaults():
    settings = get_settings()
    assert settings.llm_provider == "mock"
    assert settings.openai_api_key == ""
    assert settings.database_url.startswith("sqlite")
