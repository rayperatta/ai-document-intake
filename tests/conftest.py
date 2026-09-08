"""Isolate persistence and keep the test suite free of external integrations."""

import pytest

from docintake.config import get_settings
from docintake.db.database import reset_engine


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    # File SQLite is shared by API/Prefect worker threads, unlike :memory:.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'documents.db'}")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "")
    reset_engine()
    get_settings.cache_clear()
    yield
    reset_engine()
    get_settings.cache_clear()
