"""SQLAlchemy ORM models for the document intake pipeline.

Tables:
    documents — one row per submitted document, keyed by content_hash
                (idempotent: re-submitting the same content returns the
                existing record instead of creating a duplicate).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class DocumentORM(Base):
    """ORM model for a document record in the pipeline."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="file_upload")
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    extraction_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    routing_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<DocumentORM id={self.id[:8]} hash={self.content_hash[:12]} status={self.status}>"
