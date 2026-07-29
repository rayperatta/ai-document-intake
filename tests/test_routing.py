"""Tests for the routing rules engine."""

from __future__ import annotations

from docintake.models import (
    DocumentType,
    EmailData,
    ExtractionResult,
    FormData,
    InvoiceData,
    Urgency,
)
from docintake.routing.rules import HIGH_VALUE_THRESHOLD, route_document


class TestInvoiceRouting:
    def test_high_value_invoice(self):
        extraction = ExtractionResult(
            document_type=DocumentType.INVOICE,
            confidence=0.95,
            invoice=InvoiceData(
                invoice_number="INV-1",
                vendor_name="Acme",
                invoice_date="2026-01-01",
                total_amount=15_000.00,
                currency="USD",
            ),
        )
        decision = route_document(extraction)
        assert decision.queue == "finance"
        assert decision.urgency == Urgency.HIGH

    def test_low_value_invoice(self):
        extraction = ExtractionResult(
            document_type=DocumentType.INVOICE,
            confidence=0.90,
            invoice=InvoiceData(
                invoice_number="INV-2",
                vendor_name="Acme",
                invoice_date="2026-01-01",
                total_amount=500.00,
                currency="USD",
            ),
        )
        decision = route_document(extraction)
        assert decision.queue == "finance"
        assert decision.urgency == Urgency.MEDIUM

    def test_threshold_boundary(self):
        """Amount exactly at threshold → HIGH."""
        extraction = ExtractionResult(
            document_type=DocumentType.INVOICE,
            confidence=0.90,
            invoice=InvoiceData(
                invoice_number="INV-3",
                vendor_name="Acme",
                invoice_date="2026-01-01",
                total_amount=HIGH_VALUE_THRESHOLD,
                currency="USD",
            ),
        )
        decision = route_document(extraction)
        assert decision.urgency == Urgency.HIGH

    def test_invoice_no_data(self):
        extraction = ExtractionResult(
            document_type=DocumentType.INVOICE,
            confidence=0.50,
            invoice=None,
        )
        decision = route_document(extraction)
        assert decision.queue == "manual_review"


class TestEmailRouting:
    def test_critical_email(self):
        extraction = ExtractionResult(
            document_type=DocumentType.EMAIL,
            confidence=0.90,
            email=EmailData(
                sender="alice@example.com",
                recipient="support@example.com",
                subject="URGENT: Down",
                date="2026-01-01",
                body_summary="Production down",
                urgency=Urgency.CRITICAL,
            ),
        )
        decision = route_document(extraction)
        assert decision.queue == "ops"
        assert decision.urgency == Urgency.CRITICAL

    def test_high_urgency_email(self):
        extraction = ExtractionResult(
            document_type=DocumentType.EMAIL,
            confidence=0.88,
            email=EmailData(
                sender="bob@example.com",
                recipient="support@example.com",
                subject="Important",
                date="2026-01-01",
                body_summary="Need help",
                urgency=Urgency.HIGH,
            ),
        )
        decision = route_document(extraction)
        assert decision.queue == "support"
        assert decision.urgency == Urgency.HIGH

    def test_medium_email(self):
        extraction = ExtractionResult(
            document_type=DocumentType.EMAIL,
            confidence=0.88,
            email=EmailData(
                sender="charlie@example.com",
                recipient="support@example.com",
                subject="Question",
                date="2026-01-01",
                body_summary="Hello",
                urgency=Urgency.MEDIUM,
            ),
        )
        decision = route_document(extraction)
        assert decision.queue == "support"
        assert decision.urgency == Urgency.MEDIUM

    def test_email_no_data(self):
        extraction = ExtractionResult(
            document_type=DocumentType.EMAIL,
            confidence=0.50,
            email=None,
        )
        decision = route_document(extraction)
        assert decision.queue == "manual_review"


class TestFormRouting:
    def test_form_routed_to_onboarding(self):
        extraction = ExtractionResult(
            document_type=DocumentType.FORM,
            confidence=0.85,
            form=FormData(
                form_type="Vendor Onboarding",
                applicant_name="João",
                contact_email="joao@example.com",
            ),
        )
        decision = route_document(extraction)
        assert decision.queue == "onboarding"
        assert decision.urgency == Urgency.LOW

    def test_form_no_data(self):
        extraction = ExtractionResult(
            document_type=DocumentType.FORM,
            confidence=0.50,
            form=None,
        )
        decision = route_document(extraction)
        assert decision.queue == "manual_review"


class TestUnknownRouting:
    def test_unknown_goes_to_manual_review(self):
        extraction = ExtractionResult(
            document_type=DocumentType.UNKNOWN,
            confidence=0.20,
        )
        decision = route_document(extraction)
        assert decision.queue == "manual_review"
        assert decision.urgency == Urgency.MEDIUM
