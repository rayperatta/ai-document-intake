"""Tests for the Prefect intake pipeline flow."""

from __future__ import annotations

import os

# Force in-memory SQLite BEFORE any docintake.db imports
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest

from docintake.db.database import init_db, reset_engine
from docintake.flows.intake_flow import run_intake_pipeline
from docintake.models import DocStatus, DocumentRecord, DocumentType, RoutingDecision, Urgency
from docintake.notify.notifier import notify


@pytest.fixture(autouse=True)
def _clean_db():
    """Reset the in-memory database before each test."""
    reset_engine()
    init_db()
    yield
    reset_engine()

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
"""


class TestPipelineFlow:
    def test_invoice_pipeline(self):
        result = run_intake_pipeline(SAMPLE_INVOICE, filename="invoice.txt")
        assert result["is_duplicate"] is False
        assert result["document_type"] == "invoice"
        assert result["queue"] == "finance"
        assert result["urgency"] == "high"
        assert result["confidence"] > 0.9
        assert "notification" in result

    def test_email_pipeline(self):
        result = run_intake_pipeline(SAMPLE_EMAIL, filename="email.md")
        assert result["is_duplicate"] is False
        assert result["document_type"] == "email"
        assert result["queue"] == "ops"
        assert result["urgency"] == "critical"

    def test_form_pipeline(self):
        result = run_intake_pipeline(SAMPLE_FORM, filename="form.txt")
        assert result["is_duplicate"] is False
        assert result["document_type"] == "form"
        assert result["queue"] == "onboarding"
        assert result["urgency"] == "low"

    def test_idempotent_resubmission(self):
        """Re-submitting the same content returns the existing record."""
        r1 = run_intake_pipeline(SAMPLE_INVOICE, filename="invoice.txt")
        r2 = run_intake_pipeline(SAMPLE_INVOICE, filename="invoice.txt")
        assert r1["is_duplicate"] is False
        assert r2["is_duplicate"] is True
        assert r1["document_id"] == r2["document_id"]


class TestNotifier:
    def test_notify_logs_and_returns_payload(self):
        record = DocumentRecord(
            content_hash="abc123",
            raw_text="test",
            filename="test.txt",
            status=DocStatus.ROUTED,
            document_type=DocumentType.INVOICE,
            routing=RoutingDecision(
                queue="finance",
                urgency=Urgency.HIGH,
                reason="High-value invoice",
            ),
        )
        payload = notify(record)
        assert payload["queue"] == "finance"
        assert payload["urgency"] == "high"
        assert "webhook_status" in payload

    def test_notify_without_routing_raises(self):
        import pytest

        record = DocumentRecord(
            content_hash="abc123",
            raw_text="test",
            routing=None,
        )
        with pytest.raises(AssertionError):
            notify(record)
