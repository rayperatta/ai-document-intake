"""Tests for the LLM extraction module."""

from __future__ import annotations

import json

import pytest

from docintake.extraction.base import _detect_type
from docintake.extraction.extractor import extract_document
from docintake.extraction.mock_provider import MockProvider
from docintake.extraction.openai_provider import _parse_llm_json
from docintake.models import DocumentType, ExtractionResult, Urgency

# ── MockProvider — type detection ───────────────────────────


class TestTypeDetection:
    def test_detect_invoice(self):
        text = "INVOICE #INV-001\nBill To: Client\nTotal: $500"
        assert _detect_type(text) == DocumentType.INVOICE

    def test_detect_email(self):
        text = "From: alice@example.com\nSubject: Hello\nTo: bob@example.com"
        assert _detect_type(text) == DocumentType.EMAIL

    def test_detect_form(self):
        text = "VENDOR ONBOARDING FORM\nApplicant: John"
        assert _detect_type(text) == DocumentType.FORM

    def test_detect_unknown(self):
        text = "Lorem ipsum dolor sit amet."
        assert _detect_type(text) == DocumentType.UNKNOWN


# ── MockProvider — extraction ────────────────────────────────


SAMPLE_INVOICE = """INVOICE
From: Acme Corp
Invoice #: INV-2026-0042
Date: 2026-07-15
Due Date: 2026-08-15
Subtotal: $9,340.00
TOTAL DUE: $11,488.20
Payment terms: Net 30
"""

SAMPLE_EMAIL = """# Email — Support Request
**From:** maria@globex.example
**To:** support@raystudios.example
**Subject:** URGENT: Production down
**Date:** 2026-07-20 14:32 UTC

Hello team, production is down. This is high priority. Please escalate.
"""

SAMPLE_FORM = """VENDOR ONBOARDING FORM
Company Name: DataFlux Solutions Ltd.
Contact Person: João Pereira
Email: joao@dataflux.example
Phone: +351 210 000 000
Tax ID: PT 500 000 000
"""


class TestMockProvider:
    @pytest.fixture()
    def provider(self):
        return MockProvider()

    def test_invoice_extraction(self, provider):
        result = provider.extract(SAMPLE_INVOICE)
        assert result.document_type == DocumentType.INVOICE
        assert result.confidence == 0.92
        assert result.invoice is not None
        assert result.invoice.invoice_number == "INV-2026-0042"
        assert result.invoice.vendor_name == "Acme Corp"
        assert result.invoice.invoice_date == "2026-07-15"
        assert result.invoice.due_date == "2026-08-15"
        assert result.invoice.total_amount == 11488.20
        assert result.invoice.currency == "USD"
        assert result.invoice.payment_terms == "Net 30"

    def test_email_extraction(self, provider):
        result = provider.extract(SAMPLE_EMAIL)
        assert result.document_type == DocumentType.EMAIL
        assert result.confidence == 0.88
        assert result.email is not None
        assert "maria" in result.email.sender
        assert "URGENT" in result.email.subject
        assert result.email.urgency == Urgency.CRITICAL
        assert result.email.body_summary

    def test_form_extraction(self, provider):
        result = provider.extract(SAMPLE_FORM)
        assert result.document_type == DocumentType.FORM
        assert result.confidence == 0.85
        assert result.form is not None
        assert "João" in result.form.applicant_name
        assert result.form.contact_email == "joao@dataflux.example"
        assert result.form.contact_phone is not None
        assert len(result.form.fields) > 0

    def test_unknown_extraction(self, provider):
        result = provider.extract("Lorem ipsum dolor sit amet.")
        assert result.document_type == DocumentType.UNKNOWN
        assert result.confidence == 0.30
        assert result.invoice is None
        assert result.email is None
        assert result.form is None

    def test_deterministic(self, provider):
        """Same input always produces the same output."""
        r1 = provider.extract(SAMPLE_INVOICE)
        r2 = provider.extract(SAMPLE_INVOICE)
        assert r1 == r2

    def test_eur_currency_detection(self, provider):
        text = "INVOICE\nFrom: EU Corp\nTotal: €1.500,00"
        result = provider.extract(text)
        assert result.invoice is not None
        assert result.invoice.currency == "EUR"


# ── Extractor with retry ────────────────────────────────────


class FailingProvider:
    """Provider that fails N times then succeeds."""

    name = "failing"

    def __init__(self, fail_count: int):
        self._fail_count = fail_count
        self._calls = 0

    def extract(self, raw_text: str) -> ExtractionResult:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise json.JSONDecodeError("bad json", "doc", 0)
        return MockProvider().extract(raw_text)


class TestExtractorRetry:
    def test_retry_then_success(self):
        provider = FailingProvider(fail_count=1)
        result = extract_document(SAMPLE_INVOICE, provider=provider)
        assert result.document_type == DocumentType.INVOICE
        assert provider._calls == 2  # 1 fail + 1 success

    def test_retry_exhausted_returns_fallback(self):
        provider = FailingProvider(fail_count=5)
        result = extract_document(SAMPLE_INVOICE, provider=provider)
        assert result.document_type == DocumentType.UNKNOWN
        assert result.confidence == 0.0
        assert provider._calls == 3  # 1 initial + 2 retries


# ── OpenAI-compatible JSON parser ───────────────────────────


class TestParseLLMJson:
    def test_parse_invoice_json(self):
        llm_output = json.dumps({
            "document_type": "invoice",
            "confidence": 0.95,
            "invoice": {
                "invoice_number": "INV-999",
                "vendor_name": "TestCorp",
                "invoice_date": "2026-07-01",
                "due_date": "2026-08-01",
                "total_amount": 500.00,
                "currency": "USD",
                "payment_terms": "Net 15",
                "line_items": [],
            },
            "email": None,
            "form": None,
            "raw_metadata": {},
        })
        result = _parse_llm_json(llm_output, DocumentType.INVOICE)
        assert result.document_type == DocumentType.INVOICE
        assert result.confidence == 0.95
        assert result.invoice is not None
        assert result.invoice.invoice_number == "INV-999"
        assert result.invoice.vendor_name == "TestCorp"

    def test_parse_email_json(self):
        llm_output = json.dumps({
            "document_type": "email",
            "confidence": 0.90,
            "invoice": None,
            "email": {
                "sender": "alice@example.com",
                "recipient": "bob@example.com",
                "subject": "Test",
                "date": "2026-07-01",
                "body_summary": "Hello",
                "urgency": "high",
            },
            "form": None,
            "raw_metadata": {},
        })
        result = _parse_llm_json(llm_output, DocumentType.EMAIL)
        assert result.document_type == DocumentType.EMAIL
        assert result.email is not None
        assert result.email.urgency == Urgency.HIGH

    def test_parse_invalid_type_falls_back(self):
        llm_output = json.dumps({
            "document_type": "nonsense",
            "confidence": 0.5,
        })
        result = _parse_llm_json(llm_output, DocumentType.UNKNOWN)
        assert result.document_type == DocumentType.UNKNOWN

    def test_parse_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_json("not json at all", DocumentType.UNKNOWN)


# ── Integration: extractor with mock provider ───────────────


class TestExtractorIntegration:
    def test_extract_invoice_end_to_end(self):
        result = extract_document(SAMPLE_INVOICE)
        assert result.document_type == DocumentType.INVOICE
        assert result.invoice is not None
        assert result.invoice.invoice_number == "INV-2026-0042"

    def test_extract_email_end_to_end(self):
        result = extract_document(SAMPLE_EMAIL)
        assert result.document_type == DocumentType.EMAIL
        assert result.email is not None
        assert result.email.urgency == Urgency.CRITICAL

    def test_extract_form_end_to_end(self):
        result = extract_document(SAMPLE_FORM)
        assert result.document_type == DocumentType.FORM
        assert result.form is not None
        assert result.form.contact_email == "joao@dataflux.example"
