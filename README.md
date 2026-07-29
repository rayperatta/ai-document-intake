# AI Document Intake Pipeline

> Inbox simulado (emails, PDFs, invoices, forms) → LLM-powered structured
> extraction → validation → Postgres persistence → automatic routing by
> type/urgency → notification. The LLM is a **component** of the pipeline, not
> the product.

[![CI](https://img.shields.io/badge/CI-ruff%20%2B%20pytest-blue)](#)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](#)
[![License](https://img.shields.io/badge/license-MIT-green)](#)

## Architecture

```mermaid
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Inbox   │───▶│ Extract  │───▶│ Validate │───▶│ Persist  │───▶│  Route   │
│ (API)    │    │ (LLM)    │    │ (Pydantic)│   │ (Postgres)│   │ (Rules)  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                                      │
                                                                ┌─────▼─────┐
                                                                │  Notify   │
                                                                │ (Webhook) │
                                                                └───────────┘
```

## Quickstart (mock mode — zero cost)

```bash
# 1. Install dependencies
make dev

# 2. Run tests
make test

# 3. Start API (mock LLM, no API keys needed)
make run-api

# 4. Submit a document
curl -X POST http://localhost:8000/documents \
  -F "file=@samples/invoice_acme_001.txt"
```

## Using a real OpenAI-compatible LLM

Set environment variables (see `.env.example`):

```bash
export LLM_PROVIDER=openai
export OPENAI_BASE_URL=https://api.openai.com/v1   # or OpenRouter, etc.
export OPENAI_API_KEY=sk-your-key-here
export LLM_MODEL=gpt-4o-mini
```

## Documentation

- [Architecture](#architecture)
- [API Reference](docs/api.md) (coming soon)
- [Routing Rules](docs/routing.md) (coming soon)

## Tech Stack

| Layer        | Technology                        |
|--------------|-----------------------------------|
| API          | FastAPI, Pydantic v2              |
| Extraction   | OpenAI-compatible client + mock   |
| Persistence  | SQLAlchemy 2.0, Postgres 16       |
| Orchestration| Prefect 3                         |
| CI/CD        | GitHub Actions (ruff + pytest)    |
| Container    | Docker Compose                    |

## License

MIT — see [LICENSE](LICENSE).
