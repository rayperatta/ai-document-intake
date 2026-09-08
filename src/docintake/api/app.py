"""FastAPI application for the document intake pipeline.

Endpoints:
    GET  /            — health check
    POST /documents   — submit a document (file upload or webhook JSON)
"""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from docintake import __version__
from docintake.config import get_settings
from docintake.flows.intake_flow import run_intake_pipeline
from docintake.models import (
    DocumentResponse,
    DocumentSubmission,
    HealthResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Document Intake Pipeline",
    description="Inbox → LLM extraction → validation → persistence → routing → notification",
    version=__version__,
)


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
        if (
            file.content_type == "application/pdf"
            or (file.filename or "").lower().endswith(".pdf")
            or raw_bytes.startswith(b"%PDF-")
        ):
            raise HTTPException(
                status_code=415, detail="PDF extraction is not supported; submit UTF-8 text."
            )
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=415, detail="File must contain UTF-8 text") from exc
        if "\x00" in raw_text:
            raise HTTPException(status_code=415, detail="Binary files are not supported")
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

    # The synchronous Prefect flow runs off the event loop. This endpoint waits
    # for persisted extraction and routing; it does not merely acknowledge intake.
    result = await run_in_threadpool(
        run_intake_pipeline, raw_text, filename=filename, source=source
    )
    return DocumentResponse(
        id=result["document_id"],
        status=result["status"],
        content_hash=result["content_hash"],
        message="Document processed; routing persisted.",
        is_duplicate=result["is_duplicate"],
        document_type=result["document_type"],
        routing=result["routing"],
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors — return a clean 500."""
    logger.exception("Unhandled error processing request: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal pipeline error; resubmit the same text to resume."},
    )
