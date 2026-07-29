"""Repository layer — data access with idempotent insertion.

The repository is the single access point for document persistence.
Re-submitting identical content (same SHA-256 hash) returns the existing
record instead of creating a duplicate, making the intake API idempotent.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from docintake.db.models import DocumentORM
from docintake.models import (
    DocStatus,
    DocumentRecord,
    DocumentType,
    ExtractionResult,
    RoutingDecision,
)

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Data access for document records with idempotent insertion."""

    def __init__(self, session: Session):
        self._session = session

    # ── Read ───────────────────────────────────────────────────

    def get_by_id(self, doc_id: str) -> DocumentRecord | None:
        """Fetch a document by its UUID."""
        orm = self._session.get(DocumentORM, doc_id)
        return self._to_record(orm) if orm else None

    def get_by_hash(self, content_hash: str) -> DocumentRecord | None:
        """Fetch a document by its content hash (for idempotency check)."""
        stmt = select(DocumentORM).where(DocumentORM.content_hash == content_hash)
        orm = self._session.execute(stmt).scalar_one_or_none()
        return self._to_record(orm) if orm else None

    def list_documents(self, limit: int = 100) -> list[DocumentRecord]:
        """List recent documents, newest first."""
        stmt = select(DocumentORM).order_by(DocumentORM.received_at.desc()).limit(limit)
        orms = self._session.execute(stmt).scalars().all()
        return [self._to_record(orm) for orm in orms]

    # ── Write (idempotent) ─────────────────────────────────────

    def save_or_get(self, record: DocumentRecord) -> tuple[DocumentRecord, bool]:
        """Insert a document, or return existing if content_hash matches.

        Returns:
            (record, is_duplicate) — if is_duplicate, the record was already
            present and the existing one is returned.
        """
        existing = self.get_by_hash(record.content_hash)
        if existing is not None:
            logger.info(
                "Duplicate document detected: hash=%s, id=%s",
                record.content_hash[:12],
                existing.id,
            )
            return existing, True

        orm = DocumentORM(
            id=str(record.id),
            content_hash=record.content_hash,
            raw_text=record.raw_text,
            filename=record.filename,
            source=record.source,
            status=record.status.value,
            document_type=record.document_type.value,
            extraction_json=record.extraction.model_dump() if record.extraction else None,
            routing_json=record.routing.model_dump() if record.routing else None,
            received_at=record.received_at,
            processed_at=record.processed_at,
        )
        self._session.add(orm)
        self._session.flush()
        logger.info("Document saved: hash=%s, id=%s", record.content_hash[:12], orm.id)
        return self._to_record(orm), False

    # ── Update ─────────────────────────────────────────────────

    def update_extraction(
        self,
        doc_id: str,
        extraction: ExtractionResult,
    ) -> DocumentRecord | None:
        """Update a document with extraction results and advance status."""
        orm = self._session.get(DocumentORM, doc_id)
        if orm is None:
            return None
        orm.extraction_json = extraction.model_dump()
        orm.document_type = extraction.document_type.value
        orm.status = DocStatus.EXTRACTED.value
        self._session.flush()
        return self._to_record(orm)

    def update_routing(
        self,
        doc_id: str,
        routing: RoutingDecision,
    ) -> DocumentRecord | None:
        """Update a document with routing decision and advance status."""
        orm = self._session.get(DocumentORM, doc_id)
        if orm is None:
            return None
        orm.routing_json = routing.model_dump()
        orm.status = DocStatus.ROUTED.value
        orm.processed_at = datetime.now(UTC)
        self._session.flush()
        return self._to_record(orm)

    # ── Mapping ───────────────────────────────────────────────

    @staticmethod
    def _to_record(orm: DocumentORM | None) -> DocumentRecord | None:
        if orm is None:
            return None
        extraction = None
        if orm.extraction_json:
            extraction = ExtractionResult.model_validate(orm.extraction_json)

        routing = None
        if orm.routing_json:
            routing = RoutingDecision.model_validate(orm.routing_json)

        return DocumentRecord(
            id=orm.id,  # type: ignore[arg-type]
            content_hash=orm.content_hash,
            raw_text=orm.raw_text,
            filename=orm.filename,
            source=orm.source,
            status=DocStatus(orm.status),
            document_type=DocumentType(orm.document_type),
            extraction=extraction,
            routing=routing,
            received_at=orm.received_at,
            processed_at=orm.processed_at,
        )
