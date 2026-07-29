"""OpenAI-compatible LLM provider.

Reads configuration from environment variables — never hardcodes keys.
Works with any OpenAI-compatible API (OpenAI, OpenRouter, Together, etc.)
by setting OPENAI_BASE_URL, OPENAI_API_KEY, and LLM_MODEL.

This provider is only activated when LLM_PROVIDER=openai is set.
No real API keys are used in tests or CI.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from docintake.config import get_settings
from docintake.extraction.base import _detect_type
from docintake.models import (
    DocumentType,
    EmailData,
    ExtractionResult,
    FormData,
    InvoiceData,
    Urgency,
)

logger = logging.getLogger(__name__)

# System prompt instructs the LLM to return strict JSON matching our schema.
_SYSTEM_PROMPT = """\
You are a document extraction engine. Analyze the given document text and return
a JSON object matching this schema:

{{
  "document_type": "invoice" | "email" | "form" | "unknown",
  "confidence": 0.0-1.0,
  "invoice": {{
    "invoice_number": "string",
    "vendor_name": "string",
    "invoice_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD or null",
    "total_amount": number,
    "currency": "USD|EUR|GBP",
    "payment_terms": "string or null",
    "line_items": []
  }},
  "email": {{
    "sender": "string",
    "recipient": "string",
    "subject": "string",
    "date": "string",
    "body_summary": "string (max 300 chars)",
    "urgency": "low|medium|high|critical"
  }},
  "form": {{
    "form_type": "string",
    "applicant_name": "string",
    "contact_email": "string or null",
    "contact_phone": "string or null",
    "fields": {{}}
  }},
  "raw_metadata": {{}}
}}

Rules:
- Only fill the object matching the detected document_type. Set others to null.
- If you cannot determine a field, use null or an empty string.
- Return ONLY valid JSON — no markdown, no explanation.
"""


class OpenAICompatibleProvider:
    """LLM provider using any OpenAI-compatible API.

    Configuration via env vars:
        OPENAI_BASE_URL — API base URL (e.g. https://api.openai.com/v1)
        OPENAI_API_KEY  — API key (NEVER hardcoded in source)
        LLM_MODEL       — Model name (e.g. gpt-4o-mini)
    """

    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Either set the key or use LLM_PROVIDER=mock (default)."
            )
        self._base_url = settings.openai_base_url
        self._api_key = settings.openai_api_key
        self._model = settings.llm_model
        # Import here so tests don't require the openai package to be configured
        from openai import OpenAI  # type: ignore[import-untyped]

        self._client: Any = OpenAI(base_url=self._base_url, api_key=self._api_key)

    def extract(self, raw_text: str) -> ExtractionResult:
        """Call the OpenAI-compatible API and parse the response."""
        # Use heuristic type detection to guide the prompt
        doc_type = _detect_type(raw_text)

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        logger.debug("LLM response: %s", content)
        return _parse_llm_json(content, doc_type)


def _parse_llm_json(content: str, fallback_type: DocumentType) -> ExtractionResult:
    """Parse JSON from LLM response and validate with Pydantic models."""
    data = json.loads(content)

    doc_type_str = data.get("document_type", fallback_type.value)
    try:
        doc_type = DocumentType(doc_type_str)
    except ValueError:
        doc_type = fallback_type

    confidence = float(data.get("confidence", 0.5))

    invoice = None
    email = None
    form = None

    if doc_type == DocumentType.INVOICE and data.get("invoice"):
        inv = data["invoice"]
        invoice = InvoiceData(
            invoice_number=inv.get("invoice_number", ""),
            vendor_name=inv.get("vendor_name", ""),
            invoice_date=inv.get("invoice_date", ""),
            due_date=inv.get("due_date"),
            total_amount=float(inv.get("total_amount", 0)),
            currency=inv.get("currency", "USD"),
            payment_terms=inv.get("payment_terms"),
            line_items=inv.get("line_items", []),
        )

    if doc_type == DocumentType.EMAIL and data.get("email"):
        em = data["email"]
        urgency_str = em.get("urgency", "medium")
        try:
            urgency = Urgency(urgency_str)
        except ValueError:
            urgency = Urgency.MEDIUM
        email = EmailData(
            sender=em.get("sender", ""),
            recipient=em.get("recipient", ""),
            subject=em.get("subject", ""),
            date=em.get("date", ""),
            body_summary=em.get("body_summary", ""),
            urgency=urgency,
        )

    if doc_type == DocumentType.FORM and data.get("form"):
        fm = data["form"]
        form = FormData(
            form_type=fm.get("form_type", ""),
            applicant_name=fm.get("applicant_name", ""),
            contact_email=fm.get("contact_email"),
            contact_phone=fm.get("contact_phone"),
            fields=fm.get("fields", {}),
        )

    return ExtractionResult(
        document_type=doc_type,
        confidence=confidence,
        invoice=invoice,
        email=email,
        form=form,
        raw_metadata={"provider": "openai", "model": data.get("raw_metadata", {})},
    )
