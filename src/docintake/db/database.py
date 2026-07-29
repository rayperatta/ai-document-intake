"""Database engine and session management.

Reads DATABASE_URL from settings. Defaults to a local SQLite file for
development and testing. In Docker Compose, a Postgres URL is used.

Usage:
    from docintake.db.database import get_session, init_db

    init_db()                       # create tables (dev/test only)
    with get_session() as session:  # scoped session context manager
        ...
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from docintake.config import get_settings
from docintake.db.models import Base

logger = logging.getLogger(__name__)

# Lazy engine creation — allows tests to override DATABASE_URL before first use
_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, echo=False, connect_args=connect_args)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
        logger.info("Database engine created: %s", url.split("@")[-1] if "@" in url else url)
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a scoped SQLAlchemy session; commit + close on exit."""
    _get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables — use in dev/test only (use Alembic in production)."""
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


def reset_engine() -> None:
    """Reset the cached engine and session factory.

    Useful in tests when DATABASE_URL changes between test modules.
    """
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
