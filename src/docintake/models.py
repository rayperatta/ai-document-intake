"""Pydantic models for the document intake pipeline.

These models define the contract between the API, the extraction layer,
and the persistence layer. Pydantic v2 is used throughout for validation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    """Supported document types for structured extraction."""

    INVOICE = "invoice"
    EMAIL = "email"
    FORM = "form"
    UNKNOWN = "unknown"


class Urgency(StrEnum):
    """Urgency levels used by the routing engine."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DocStatus(StrEnum):
    """Lifecycle status of a document in the pipeline."""

    RECEIVED = "received"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    ROUTED = "routed"
    NOTIFIED = "notified"
    FAILED = "failed"


# ── Input models ─────────────────────────────────────────────


class DocumentSubmission(BaseModel):
    """Inbound document — either from a webhook or file upload."""

    raw_text: str = Field(..., min_length=1, description="Raw document content")
    filename: str | None = Field(default=None, description="Original filename if known")
    content_type: str | None = Field(
        default=None, description="MIME type (e.g. text/plain, application/pdf)"
    )
    source: Literal["webhook", "file_upload"] = Field(
        default="file_upload", description="How the document entered the pipeline"
    )

    model_config = {"extra": "ignore"}


# ── Extraction output models ─────────────────────────────────


class InvoiceData(BaseModel):
    """Structured data extracted from an invoice."""

    invoice_number: str
    vendor_name: str
    invoice_date: str
    due_date: str | None = None
    total_amount: float
    currency: str = "USD"
    payment_terms: str | None = None
    line_items: list[dict] = Field(default_factory=list)


class EmailData(BaseModel):
    """Structured data extracted from an email message."""

    sender: str
    recipient: str
    subject: str
    date: str
    body_summary: str
    urgency: Urgency = Urgency.MEDIUM


class FormData(BaseModel):
    """Structured data extracted from a form."""

    form_type: str
    applicant_name: str
    contact_email: str | None = None
    contact_phone: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Output of the LLM extraction step — validated structured data."""

    document_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    invoice: InvoiceData | None = None
    email: EmailData | None = None
    form: FormData | None = None
    raw_metadata: dict = Field(default_factory=dict)


# ── Pipeline output models ───────────────────────────────────


class RoutingDecision(BaseModel):
    """Routing decision produced by the rules engine."""

    queue: str
    urgency: Urgency
    reason: str


class DocumentRecord(BaseModel):
    """Full record of a document as stored in the pipeline."""

    id: UUID = Field(default_factory=uuid4)
    content_hash: str
    raw_text: str
    filename: str | None = None
    source: str = "file_upload"
    status: DocStatus = DocStatus.RECEIVED
    document_type: DocumentType = DocumentType.UNKNOWN
    extraction: ExtractionResult | None = None
    routing: RoutingDecision | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """API response for document submission."""

    id: UUID
    status: DocStatus
    content_hash: str
    message: str
    is_duplicate: bool = False
    document_type: DocumentType | None = None
    routing: RoutingDecision | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["ok", "degraded"]
    version: str
    llm_provider: str
