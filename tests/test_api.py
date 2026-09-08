"""Tests for the FastAPI intake API."""

import pytest
from fastapi.testclient import TestClient

from docintake.api.app import app
from docintake.db.database import get_session
from docintake.db.repository import DocumentRepository

client = TestClient(app)


# ── Health ───────────────────────────────────────────────────


def test_health_root():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"


def test_health_alias():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── POST /documents — file upload ────────────────────────────


def test_submit_file_upload():
    r = client.post(
        "/documents",
        files={
        "file": (
            "invoice_acme_001.txt",
            b"INVOICE from Acme Corp\nTotal: $5,000",
            "text/plain",
        )
    },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "routed"
    assert len(body["content_hash"]) == 64  # SHA-256 hex
    assert body["document_type"] == "invoice"
    assert not body["is_duplicate"]
    assert body["routing"]["queue"] == "finance"
    with get_session() as session:
        saved = DocumentRepository(session).get_by_id(body["id"])
        assert saved is not None
        assert saved.extraction is not None
        assert saved.routing is not None
        assert saved.source == "file_upload"


def test_submit_file_empty_rejected():
    r = client.post("/documents", files={"file": ("empty.txt", b"", "text/plain")})
    assert r.status_code == 422


# ── POST /documents — webhook JSON ───────────────────────────


def test_submit_webhook_json():
    r = client.post(
        "/documents",
        json={
            "raw_text": "URGENT: Production dashboard down since 14:00",
            "filename": "email_support.md",
            "source": "webhook",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "routed"
    assert body["content_hash"]


def test_submit_webhook_empty_text_rejected():
    r = client.post("/documents", json={"raw_text": "   "})
    assert r.status_code == 422


# ── POST /documents — validation ─────────────────────────────


def test_submit_no_body_rejected():
    r = client.post("/documents")
    assert r.status_code == 422


def test_content_hash_deterministic():
    """Same content → same hash (idempotency prerequisite)."""
    payload = {"file": ("test.txt", b"Same content", "text/plain")}
    h1 = client.post("/documents", files=payload).json()["content_hash"]
    h2 = client.post("/documents", files=payload).json()["content_hash"]
    assert h1 == h2


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("document.pdf", b"%PDF-1.7 fake sample", "application/pdf"),
        ("disguised.txt", b"%PDF-1.7 fake sample", "text/plain"),
        ("binary.txt", b"\xff\xfe", "text/plain"),
        ("binary.txt", b"abc\x00def", "text/plain"),
    ],
)
def test_unsupported_files_rejected(filename, content, content_type):
    response = client.post(
        "/documents", files={"file": (filename, content, content_type)}
    )
    assert response.status_code == 415


def test_api_resubmission_returns_persisted_routing():
    payload = {"raw_text": "INVOICE from Acme Corp\nTotal: $5,000", "source": "webhook"}
    first = client.post("/documents", json=payload)
    second = client.post("/documents", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["is_duplicate"] is True
    assert first.json()["routing"] == second.json()["routing"]
    with get_session() as session:
        records = DocumentRepository(session).list_documents()
        assert len(records) == 1
        assert records[0].source == "webhook"


def test_api_recovers_after_extraction_failure(monkeypatch):
    from docintake.flows import intake_flow

    original = intake_flow.extract_document
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated provider failure with private details")
        return original(*args, **kwargs)

    monkeypatch.setattr(intake_flow, "extract_document", fail_once)
    payload = {"raw_text": "INVOICE from Acme Corp\nTotal: $5,000"}
    with TestClient(app, raise_server_exceptions=False) as failure_client:
        failed = failure_client.post("/documents", json=payload)
        assert failed.status_code == 500
        assert "private details" not in failed.text
        with get_session() as session:
            pending = DocumentRepository(session).list_documents()
            assert len(pending) == 1
            pending_id = str(pending[0].id)
            assert pending[0].status == "received"
        recovered = failure_client.post("/documents", json=payload)
    assert recovered.status_code == 201
    assert recovered.json()["id"] == pending_id
    assert recovered.json()["is_duplicate"] is True
    assert recovered.json()["status"] == "routed"
    assert calls == 2
