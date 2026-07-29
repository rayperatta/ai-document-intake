"""FastAPI application for the document intake pipeline.

Endpoints:
    GET  /            — health check
    POST /documents   — submit a document (file upload or webhook JSON)
"""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from docintake import __version__
from docintake.config import get_settings
from docintake.models import (
    DocStatus,
    DocumentResponse,
    DocumentSubmission,
    DocumentType,
    HealthResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Document Intake Pipeline",
    description="Inbox → LLM extraction → validation → persistence → routing → notification",
    version=__version__,
)


def _content_hash(text: str) -> str:
    """Return SHA-256 hex digest of the raw text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@app.get("/", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check — returns service status and active LLM provider."""
    settings = get_settings()
    return HealthResponse(status="ok", version=__version__, llm_provider=settings.llm_provider)


@app.post("/documents", response_model=DocumentResponse, status_code=201)
async def submit_document(
    request: Request,
    file: UploadFile | None = None,
) -> DocumentResponse:
    """Submit a document to the intake pipeline.

    Accepts either:
    - **Multipart file upload** (`file` field) for file-based intake
    - **JSON body** (`DocumentSubmission`) for webhook-style submission

    At least one of the two is required.
    """
    raw_text: str | None = None
    filename: str | None = None
    source = "file_upload"

    if file is not None:
        # ── File upload path ────────────────────────────────
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=422, detail="Uploaded file is empty")
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        filename = file.filename
        source = "file_upload"
    elif request.headers.get("content-type", "").startswith("application/json"):
        # ── Webhook JSON path ───────────────────────────────
        try:
            body = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON body: {exc}") from exc
        try:
            submission = DocumentSubmission.model_validate(body)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid submission: {exc}") from exc
        raw_text = submission.raw_text
        filename = submission.filename
        source = submission.source
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either a multipart file upload or a JSON body (DocumentSubmission).",
        )

    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=422, detail="Document text is empty")

    c_hash = _content_hash(raw_text)

    logger.info("Document received: hash=%s, filename=%s, source=%s", c_hash[:12], filename, source)

    return DocumentResponse(
        id=uuid4(),
        status=DocStatus.RECEIVED,
        content_hash=c_hash,
        message="Document received. Pending extraction.",
        document_type=DocumentType.UNKNOWN,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors — return a clean 500."""
    logger.exception("Unhandled error processing request: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal pipeline error", "error": str(exc)},
    )
