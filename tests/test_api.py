"""Tests for the FastAPI intake API."""

from fastapi.testclient import TestClient

from docintake.api.app import app

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
    assert body["status"] == "received"
    assert len(body["content_hash"]) == 64  # SHA-256 hex
    assert body["document_type"] == "unknown"
    assert not body["is_duplicate"]


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
    assert body["status"] == "received"
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
