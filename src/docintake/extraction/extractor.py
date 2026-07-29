"""Extractor module — orchestrates LLM extraction with retry logic.

Selects the provider based on LLM_PROVIDER env var (default: mock).
Retries up to 2 times on invalid JSON or validation errors.
"""

from __future__ import annotations

import json
import logging

from docintake.config import get_settings
from docintake.extraction.base import ExtractionProvider
from docintake.extraction.mock_provider import MockProvider
from docintake.extraction.openai_provider import OpenAICompatibleProvider
from docintake.models import DocumentType, ExtractionResult

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def get_provider() -> ExtractionProvider:
    """Return the configured extraction provider.

    Default: MockProvider (deterministic, zero cost).
    Set LLM_PROVIDER=openai to use the OpenAI-compatible provider.
    """
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAICompatibleProvider()
    return MockProvider()


def extract_document(raw_text: str, provider: ExtractionProvider | None = None) -> ExtractionResult:
    """Extract structured data from raw document text.

    Uses the configured provider (or an injected one for testing).
    Retries up to MAX_RETRIES times on JSON/validation errors.
    Falls back to UNKNOWN type on persistent failure.
    """
    if provider is None:
        provider = get_provider()

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 2):  # 1 initial + 2 retries
        try:
            result = provider.extract(raw_text)
            logger.info(
                "Extraction succeeded on attempt %d: type=%s, confidence=%.2f",
                attempt,
                result.document_type,
                result.confidence,
            )
            return result
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            last_error = exc
            logger.warning("Extraction attempt %d failed: %s", attempt, exc)
            if attempt > MAX_RETRIES:
                break

    # All retries exhausted — return a safe fallback
    logger.error("Extraction failed after %d attempts: %s", MAX_RETRIES + 1, last_error)
    return ExtractionResult(
        document_type=DocumentType.UNKNOWN,
        confidence=0.0,
        raw_metadata={"provider": "fallback", "error": str(last_error)},
    )
