"""Abstract provider interface for LLM extraction.

The provider is the only touchpoint with an LLM. The default MockProvider
is deterministic and requires no API keys. A real OpenAI-compatible provider
can be activated via env vars (LLM_PROVIDER=openai).
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from docintake.models import (
    DocumentType,
    EmailData,
    ExtractionResult,
    FormData,
    InvoiceData,
    Urgency,
)

logger = logging.getLogger(__name__)


class ExtractionProvider(ABC):
    """Abstract base for LLM extraction providers."""

    @abstractmethod
    def extract(self, raw_text: str) -> ExtractionResult:
        """Extract structured data from raw document text.

        Args:
            raw_text: Raw document content (plain text).

        Returns:
            Validated ExtractionResult with typed structured data.
        """
        ...


# ── Helpers for mock providers ──────────────────────────────


def _detect_type(raw_text: str) -> DocumentType:
    """Heuristic document type detection from keywords."""
    text_lower = raw_text.lower()
    if any(kw in text_lower for kw in ("invoice", "bill to", "payment terms", "subtotal")):
        return DocumentType.INVOICE
    if any(kw in text_lower for kw in ("from:", "subject:", "re:", "fw:", "sent:")):
        return DocumentType.EMAIL
    if any(kw in text_lower for kw in ("form", "onboarding", "application", "applicant")):
        return DocumentType.FORM
    return DocumentType.UNKNOWN


def _parse_invoice(raw_text: str) -> InvoiceData:
    """Parse invoice fields from raw text using regex."""
    def _find(pattern: str, default: str = "") -> str:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    invoice_number = _find(r"invoice\s*#\s*:?\s*([A-Za-z0-9\-]+)", "UNKNOWN")
    vendor_name = _find(r"from:\s*(.+)", "Unknown Vendor")
    invoice_date = _find(r"date:\s*(\d{4}-\d{2}-\d{2})", "2026-01-01")
    due_date = _find(r"due date:\s*(\d{4}-\d{2}-\d{2})") or None
    payment_terms = _find(r"payment terms:\s*(.+)") or None

    # Extract total — prioritize "TOTAL DUE" over "Subtotal"
    total_match = re.search(r"total\s+due\s*:?\s*\$?([\d,]+\.?\d*)", raw_text, re.IGNORECASE)
    if not total_match:
        # Fall back to "TOTAL:" (not subtotal)
        total_match = re.search(r"(?<!sub)total\s*:?\s*\$?([\d,]+\.?\d*)", raw_text, re.IGNORECASE)
    if total_match:
        total_amount = float(total_match.group(1).replace(",", ""))
    else:
        total_match = re.search(r"\$([\d,]+\.?\d*)", raw_text)
        total_amount = float(total_match.group(1).replace(",", "")) if total_match else 0.0

    # Currency detection
    currency = "EUR" if "€" in raw_text else "USD"

    return InvoiceData(
        invoice_number=invoice_number,
        vendor_name=vendor_name,
        invoice_date=invoice_date,
        due_date=due_date,
        total_amount=total_amount,
        currency=currency,
        payment_terms=payment_terms,
    )


def _parse_email(raw_text: str) -> EmailData:
    """Parse email fields from raw text using regex."""
    def _find(pattern: str, default: str = "") -> str:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    sender = _find(r"\*\*from:\*\*\s*(.+)", _find(r"from:\s*(\S+@\S+)", "unknown@example.com"))
    recipient = _find(r"\*\*to:\*\*\s*(.+)", _find(r"to:\s*(\S+@\S+)", "support@example.com"))
    subject = _find(r"\*\*subject:\*\*\s*(.+)", _find(r"subject:\s*(.+)", "(no subject)"))
    date = _find(r"\*\*date:\*\*\s*(.+)", _find(r"date:\s*(.+)", "2026-01-01"))

    # Urgency detection
    text_lower = raw_text.lower()
    if any(kw in text_lower for kw in ("urgent", "critical", "asap", "immediately")):
        urgency = Urgency.CRITICAL
    elif any(kw in text_lower for kw in ("high priority", "important", "escalate")):
        urgency = Urgency.HIGH
    elif any(kw in text_lower for kw in ("low priority", "when possible")):
        urgency = Urgency.LOW
    else:
        urgency = Urgency.MEDIUM

    # Body summary — first non-header paragraph
    lines = raw_text.split("\n")
    body_lines = [
        ln.strip()
        for ln in lines
        if ln.strip() and not ln.startswith("#") and "**" not in ln
    ]
    body_summary = " ".join(body_lines[:3])[:300]

    return EmailData(
        sender=sender,
        recipient=recipient,
        subject=subject,
        date=date,
        body_summary=body_summary,
        urgency=urgency,
    )


def _parse_form(raw_text: str) -> FormData:
    """Parse form fields from raw text using regex."""
    def _find(pattern: str, default: str = "") -> str:
        m = re.search(pattern, raw_text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    form_type = _find(r"(.+form|onboarding|application)", "Generic Form")
    applicant_name = _find(r"contact person:\s*(.+)", _find(r"applicant name:\s*(.+)", "Unknown"))
    contact_email = _find(r"email:\s*(\S+@\S+)") or None
    contact_phone = _find(r"phone:\s*(.+[\d\+\-\s])") or None

    # Collect all "Key: Value" pairs as fields
    fields: dict[str, str] = {}
    for m in re.finditer(r"^([A-Z][A-Za-z\s]+):\s*(.+)$", raw_text, re.MULTILINE):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key and val and key not in ("From", "To", "Date", "Subject"):
            fields[key] = val

    return FormData(
        form_type=form_type,
        applicant_name=applicant_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        fields=fields,
    )
