"""Tests for the persistence layer — SQLAlchemy models + idempotent repository.

Uses an in-memory SQLite database for fast, isolated tests.
"""

from __future__ import annotations

import os

# Force in-memory SQLite BEFORE any docintake.db imports
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy.orm import Session

from docintake.db.database import get_session, init_db, reset_engine
from docintake.db.models import DocumentORM
from docintake.db.repository import DocumentRepository
from docintake.models import (
    DocStatus,
    DocumentRecord,
    DocumentType,
    ExtractionResult,
    RoutingDecision,
    Urgency,
)


@pytest.fixture()
def session():
    """Provide a clean in-memory SQLite session for each test."""
    reset_engine()
    init_db()
    with get_session() as s:
        yield s
    reset_engine()


@pytest.fixture()
def repo(session: Session):
    return DocumentRepository(session)


@pytest.fixture()
def sample_record():
    return DocumentRecord(
        content_hash="abc123def456",
        raw_text="INVOICE from Acme Corp\nTotal: $5,000",
        filename="invoice.txt",
        source="file_upload",
    )


# ── Idempotent save ─────────────────────────────────────────


class TestIdempotentSave:
    def test_save_new_document(self, repo, sample_record):
        record, is_dup = repo.save_or_get(sample_record)
        assert not is_dup
        assert record.content_hash == "abc123def456"
        assert record.status == DocStatus.RECEIVED

    def test_save_duplicate_returns_existing(self, repo, sample_record):
        # First save
        record1, is_dup1 = repo.save_or_get(sample_record)
        assert not is_dup1
        original_id = record1.id

        # Second save — same content hash
        record2, is_dup2 = repo.save_or_get(sample_record)
        assert is_dup2
        assert record2.id == original_id  # same record returned

    def test_save_different_content_creates_new(self, repo, sample_record):
        repo.save_or_get(sample_record)
        other = DocumentRecord(
            content_hash="different_hash_999",
            raw_text="Different content",
        )
        record, is_dup = repo.save_or_get(other)
        assert not is_dup
        assert record.content_hash == "different_hash_999"


# ── Read operations ─────────────────────────────────────────


class TestReadOperations:
    def test_get_by_id(self, repo, sample_record):
        saved, _ = repo.save_or_get(sample_record)
        fetched = repo.get_by_id(str(saved.id))
        assert fetched is not None
        assert fetched.content_hash == sample_record.content_hash

    def test_get_by_id_not_found(self, repo):
        result = repo.get_by_id("nonexistent-uuid")
        assert result is None

    def test_get_by_hash(self, repo, sample_record):
        repo.save_or_get(sample_record)
        fetched = repo.get_by_hash("abc123def456")
        assert fetched is not None
        assert fetched.raw_text == sample_record.raw_text

    def test_get_by_hash_not_found(self, repo):
        assert repo.get_by_hash("nonexistent") is None

    def test_list_documents(self, repo):
        for i in range(5):
            repo.save_or_get(DocumentRecord(
                content_hash=f"hash_{i}",
                raw_text=f"Document {i}",
            ))
        docs = repo.list_documents()
        assert len(docs) == 5

    def test_list_documents_limit(self, repo):
        for i in range(10):
            repo.save_or_get(DocumentRecord(
                content_hash=f"hash_{i}",
                raw_text=f"Document {i}",
            ))
        docs = repo.list_documents(limit=3)
        assert len(docs) == 3


# ── Update operations ───────────────────────────────────────


class TestUpdateOperations:
    def test_update_extraction(self, repo, sample_record):
        saved, _ = repo.save_or_get(sample_record)
        extraction = ExtractionResult(
            document_type=DocumentType.INVOICE,
            confidence=0.92,
            raw_metadata={"provider": "mock"},
        )
        updated = repo.update_extraction(str(saved.id), extraction)
        assert updated is not None
        assert updated.status == DocStatus.EXTRACTED
        assert updated.document_type == DocumentType.INVOICE
        assert updated.extraction is not None
        assert updated.extraction.confidence == 0.92

    def test_update_routing(self, repo, sample_record):
        saved, _ = repo.save_or_get(sample_record)
        routing = RoutingDecision(
            queue="finance",
            urgency=Urgency.HIGH,
            reason="High-value invoice",
        )
        updated = repo.update_routing(str(saved.id), routing)
        assert updated is not None
        assert updated.status == DocStatus.ROUTED
        assert updated.routing is not None
        assert updated.routing.queue == "finance"
        assert updated.processed_at is not None

    def test_update_nonexistent_returns_none(self, repo):
        result = repo.update_extraction("nonexistent", ExtractionResult(
            document_type=DocumentType.UNKNOWN,
            confidence=0.0,
        ))
        assert result is None


# ── ORM model ───────────────────────────────────────────────


class TestDocumentORM:
    def test_orm_repr(self):
        orm = DocumentORM(
            id="test-id",
            content_hash="abc123",
            raw_text="test",
        )
        assert "DocumentORM" in repr(orm)
        assert "abc123" in repr(orm)

    def test_table_created(self, session):
        # Verify the table exists by inserting and querying
        orm = DocumentORM(content_hash="test", raw_text="hello")
        session.add(orm)
        session.flush()
        fetched = session.get(DocumentORM, orm.id)
        assert fetched is not None
        assert fetched.raw_text == "hello"
