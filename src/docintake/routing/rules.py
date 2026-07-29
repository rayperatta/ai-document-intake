"""Rules-based routing engine.

Determines which queue a document should be routed to based on its
document type, extracted data (amount, urgency), and configurable thresholds.

Examples:
    invoice + high_amount  → finance queue, HIGH
    email   + critical     → ops queue, CRITICAL
    form                    → onboarding queue, LOW
    unknown                → manual_review queue, MEDIUM
"""

from __future__ import annotations

import logging

from docintake.models import (
    DocumentType,
    ExtractionResult,
    RoutingDecision,
    Urgency,
)

logger = logging.getLogger(__name__)

# Configurable thresholds
HIGH_VALUE_THRESHOLD = 10_000.0  # invoices above this → high urgency


def route_document(extraction: ExtractionResult) -> RoutingDecision:
    """Apply routing rules to an extraction result.

    Returns a RoutingDecision with the target queue, urgency, and reason.
    """
    doc_type = extraction.document_type

    if doc_type == DocumentType.INVOICE:
        return _route_invoice(extraction)
    if doc_type == DocumentType.EMAIL:
        return _route_email(extraction)
    if doc_type == DocumentType.FORM:
        return _route_form(extraction)
    return _route_unknown(extraction)


def _route_invoice(extraction: ExtractionResult) -> RoutingDecision:
    """Route invoices based on total amount."""
    if extraction.invoice is None:
        return RoutingDecision(
            queue="manual_review",
            urgency=Urgency.MEDIUM,
            reason="Invoice type detected but no invoice data extracted",
        )

    amount = extraction.invoice.total_amount
    if amount >= HIGH_VALUE_THRESHOLD:
        return RoutingDecision(
            queue="finance",
            urgency=Urgency.HIGH,
            reason=f"High-value invoice ({amount:,.2f} {extraction.invoice.currency})",
        )
    return RoutingDecision(
        queue="finance",
        urgency=Urgency.MEDIUM,
        reason=f"Standard invoice ({amount:,.2f} {extraction.invoice.currency})",
    )


def _route_email(extraction: ExtractionResult) -> RoutingDecision:
    """Route emails based on detected urgency."""
    if extraction.email is None:
        return RoutingDecision(
            queue="manual_review",
            urgency=Urgency.MEDIUM,
            reason="Email type detected but no email data extracted",
        )

    urgency = extraction.email.urgency
    if urgency == Urgency.CRITICAL:
        return RoutingDecision(
            queue="ops",
            urgency=Urgency.CRITICAL,
            reason=f"Critical email from {extraction.email.sender}: {extraction.email.subject}",
        )
    if urgency == Urgency.HIGH:
        return RoutingDecision(
            queue="support",
            urgency=Urgency.HIGH,
            reason=f"High-priority email from {extraction.email.sender}",
        )
    return RoutingDecision(
        queue="support",
        urgency=Urgency.MEDIUM,
        reason=f"Standard email from {extraction.email.sender}",
    )


def _route_form(extraction: ExtractionResult) -> RoutingDecision:
    """Route forms to onboarding queue."""
    if extraction.form is None:
        return RoutingDecision(
            queue="manual_review",
            urgency=Urgency.MEDIUM,
            reason="Form type detected but no form data extracted",
        )
    return RoutingDecision(
        queue="onboarding",
        urgency=Urgency.LOW,
        reason=f"Form: {extraction.form.form_type} from {extraction.form.applicant_name}",
    )


def _route_unknown(extraction: ExtractionResult) -> RoutingDecision:
    """Route unrecognized documents to manual review."""
    return RoutingDecision(
        queue="manual_review",
        urgency=Urgency.MEDIUM,
        reason=f"Unknown document type (confidence={extraction.confidence:.2f})",
    )
