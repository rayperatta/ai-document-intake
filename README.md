# AI Document Intake

An independent Python portfolio project for turning text documents into structured records and routing decisions. **The API runs the processing flow and persists the result before responding.** A deterministic mock extractor lets you demonstrate the workflow locally without a paid model or external services.

**Status:** local prototype with tests. It supports UTF-8 text uploads and JSON containing extracted text. PDF parsing/OCR, authenticated deployment and reliable notification delivery remain further work.

[![CI](https://github.com/rayperatta/ai-document-intake/actions/workflows/ci.yml/badge.svg)](https://github.com/rayperatta/ai-document-intake/actions/workflows/ci.yml)

## What you can demonstrate

1. Submit invoice, email or form text through `POST /documents`.
2. Run structured extraction with a mock or OpenAI-compatible provider; validate the result with Pydantic.
3. Persist the document, extraction and routing decision using SQLAlchemy (local SQLite by default; PostgreSQL configuration in Docker Compose).
4. Route to a queue using explicit document-type and urgency rules.
5. Resubmit identical text: reuse the persisted record and routing. If extraction or routing failed, resume from the last persisted stage.

```text
UTF-8 upload / JSON text
        ↓
FastAPI → Prefect flow → save/retrieve by content hash
                              ↓
                     extract + validate → persist
                              ↓
                         route → persist → log / optional webhook
                              ↓
                  API response: ID, status, routing
```

## Run the local mock demo

Requires Python 3.12 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

export LLM_PROVIDER=mock
export DATABASE_URL=sqlite:///./docintake.db
export NOTIFY_WEBHOOK_URL=  # Disable external notifications for the local demo.
uvicorn docintake.api.app:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8000/documents \
  -F 'file=@samples/invoice_acme_001.txt'
```

Expect HTTP `201`, `status: "routed"`, a document ID, content hash and routing decision. Repeat the command: the ID stays the same and `is_duplicate` becomes `true`. Processing is synchronous from the caller’s perspective; the first request can take longer while Prefect starts its local server.

JSON is also supported:

```bash
curl -sS http://127.0.0.1:8000/documents \
  -H 'Content-Type: application/json' \
  -d '{"raw_text":"INVOICE from Acme Corp\nTotal: $5,000","source":"webhook"}'
```

Interactive endpoint documentation: [local Swagger UI](http://127.0.0.1:8000/docs). PDF uploads and invalid UTF-8 return `415`; empty text returns `422`. Send the extracted text of a PDF as JSON if text extraction has already happened elsewhere.

## Failure recovery and verification

```bash
ruff check .
pytest -q
# Focused API/persistence and recovery checks:
pytest -q tests/test_api.py tests/test_flows.py
```

The tests use temporary SQLite databases and the mock provider. They check that API submissions persist extracted data and routing, identical submissions keep one record, an extraction failure returns a clean error and can be resumed, and a routing failure reuses the saved extraction on retry. Unsupported file tests ensure PDF bytes are not silently treated as text.

These tests establish local workflow behavior; they do not establish production scale, model accuracy, PostgreSQL concurrency behavior or business savings. Mock confidence values are sample outputs, not measured extraction accuracy.

## Optional model integration

See [.env.example](.env.example) and set `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `LLM_MODEL` for an OpenAI-compatible provider. Requests may incur provider costs. Validate model outputs against a labeled document set before relying on them operationally.

## Current boundaries

- Text intake only: no PDF parser, OCR or email attachment retrieval.
- No authentication, tenant isolation, upload-size limits or background job API. Keep the demo bound to localhost and use sample documents.
- Recovery covers sequential resubmissions. Concurrent duplicate submissions are not coordinated with locks or a durable job queue.
- Once routing is persisted, a duplicate returns it without sending another notification. Webhook failures are logged; there is no durable outbox or guaranteed delivery/retry.
- Local table creation uses SQLAlchemy `create_all`; production migrations are not supplied.
- No published real-model extraction benchmark, deployment or client outcome is claimed.

## Source guide

- [API and input handling](src/docintake/api/app.py)
- [Prefect orchestration and recovery](src/docintake/flows/intake_flow.py)
- [Repository and persistence](src/docintake/db/repository.py)
- [Routing rules](src/docintake/routing/rules.py)
- [Tests](tests) and [sample documents](samples)

Python · FastAPI · Pydantic · SQLAlchemy · Prefect · PostgreSQL/SQLite · Docker · GitHub Actions

MIT — see [LICENSE](LICENSE).
