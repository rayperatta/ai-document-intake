"""Prefect flow — end-to-end document intake pipeline.

Flow: intake → extract → route → persist → notify

Each step is a Prefect task so it shows up in the Prefect UI with
retries, state tracking, and logging. The flow can be run:
- Locally (no Prefect server needed — ephemeral)
- With a Prefect server (for production orchestration)

Usage:
    from docintake.flows.intake_flow import run_intake_pipeline
    result = run_intake_pipeline(raw_text="INVOICE ...")
"""

from __future__ import annotations

import logging
from typing import Any

from prefect import flow, task

from docintake.db.database import get_session, init_db
from docintake.db.repository import DocumentRepository
from docintake.extraction.extractor import extract_document, get_provider
from docintake.models import (
    DocumentRecord,
    ExtractionResult,
    RoutingDecision,
)
from docintake.notify.notifier import notify
from docintake.routing.rules import route_document

logger = logging.getLogger(__name__)


@task
def intake_task(raw_text: str, filename: str | None = None) -> DocumentRecord:
    """Create a DocumentRecord from raw text input."""
    import hashlib

    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return DocumentRecord(
        content_hash=content_hash,
        raw_text=raw_text,
        filename=filename,
        source="pipeline",
    )


@task
def persist_task(record: DocumentRecord) -> tuple[DocumentRecord, bool]:
    """Persist the document (idempotent by content hash)."""
    init_db()
    with get_session() as session:
        repo = DocumentRepository(session)
        saved, is_dup = repo.save_or_get(record)
        return saved, is_dup


@task
def extract_task(record: DocumentRecord) -> ExtractionResult:
    """Extract structured data using the configured LLM provider."""
    provider = get_provider()
    return extract_document(record.raw_text, provider=provider)


@task
def update_extraction_task(record: DocumentRecord, extraction: ExtractionResult) -> DocumentRecord:
    """Update the persisted record with extraction results."""
    with get_session() as session:
        repo = DocumentRepository(session)
        updated = repo.update_extraction(str(record.id), extraction)
        if updated is None:
            logger.warning("Could not update extraction for %s", record.id)
            return record
        return updated


@task
def route_task(extraction: ExtractionResult) -> RoutingDecision:
    """Apply routing rules to the extraction result."""
    return route_document(extraction)


@task
def update_routing_task(record: DocumentRecord, routing: RoutingDecision) -> DocumentRecord:
    """Update the persisted record with routing decision."""
    with get_session() as session:
        repo = DocumentRepository(session)
        updated = repo.update_routing(str(record.id), routing)
        if updated is None:
            logger.warning("Could not update routing for %s", record.id)
            return record
        return updated


@task
def notify_task(record: DocumentRecord) -> dict[str, Any]:
    """Send notification for the routed document."""
    return notify(record)


@flow(name="document-intake-pipeline", log_prints=True)
def intake_pipeline(
    raw_text: str,
    filename: str | None = None,
) -> dict[str, Any]:
    """End-to-end document intake pipeline.

    Steps: intake → persist → extract → update → route → update → notify

    Returns a summary dict with the full pipeline result.
    """
    # 1. Intake
    record = intake_task(raw_text, filename)

    # 2. Persist (idempotent)
    saved, is_dup = persist_task(record)

    if is_dup:
        logger.info("Duplicate document — returning existing record: %s", saved.id)
        return {
            "document_id": str(saved.id),
            "status": saved.status.value,
            "is_duplicate": True,
            "document_type": saved.document_type.value,
        }

    # 3. Extract
    extraction = extract_task(saved)

    # 4. Update extraction in DB
    saved = update_extraction_task(saved, extraction)

    # 5. Route
    routing = route_task(extraction)

    # 6. Update routing in DB
    saved = update_routing_task(saved, routing)

    # 7. Notify
    notification = notify_task(saved)

    return {
        "document_id": str(saved.id),
        "status": saved.status.value,
        "is_duplicate": False,
        "document_type": extraction.document_type.value,
        "confidence": extraction.confidence,
        "queue": routing.queue,
        "urgency": routing.urgency.value,
        "reason": routing.reason,
        "notification": notification,
    }


def run_intake_pipeline(raw_text: str, filename: str | None = None) -> dict[str, Any]:
    """Run the intake pipeline synchronously (convenience wrapper).

    Can be called from tests, CLI, or API without a running Prefect server.
    """
    return intake_pipeline(raw_text, filename=filename)
