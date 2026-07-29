"""Mock LLM provider — deterministic, zero-cost extraction.

This provider uses heuristics (regex + keyword matching) to simulate
structured extraction. It is the default provider so the entire pipeline
and all tests run without any API key or network call.

The output is deterministic: the same input always produces the same
ExtractionResult. This makes it ideal for testing, CI, and local development.
"""

from __future__ import annotations

from docintake.extraction.base import (
    _detect_type,
    _parse_email,
    _parse_form,
    _parse_invoice,
)
from docintake.models import (
    DocumentType,
    ExtractionResult,
    InvoiceData,
)


class MockProvider:
    """Deterministic mock LLM provider (no API keys, no network)."""

    name = "mock"

    def extract(self, raw_text: str) -> ExtractionResult:
        """Extract structured data using deterministic heuristics."""
        doc_type = _detect_type(raw_text)

        invoice: InvoiceData | None = None
        email = None
        form = None

        if doc_type == DocumentType.INVOICE:
            invoice = _parse_invoice(raw_text)
            confidence = 0.92
        elif doc_type == DocumentType.EMAIL:
            email = _parse_email(raw_text)
            confidence = 0.88
        elif doc_type == DocumentType.FORM:
            form = _parse_form(raw_text)
            confidence = 0.85
        else:
            confidence = 0.30

        return ExtractionResult(
            document_type=doc_type,
            confidence=confidence,
            invoice=invoice,
            email=email,
            form=form,
            raw_metadata={
                "provider": "mock",
                "method": "heuristic_regex",
            },
        )
