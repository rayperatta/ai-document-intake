"""Notifier — sends document routing notifications.

Default: logs to stdout (always works, zero cost).
Optional: POSTs to NOTIFY_WEBHOOK_URL if configured.

This is a stub — no real external integrations. In production, this
would dispatch to Slack, email, ticketing systems, etc.
"""

from __future__ import annotations

import logging
from typing import Any

from docintake.config import get_settings
from docintake.models import DocumentRecord

logger = logging.getLogger(__name__)


def notify(record: DocumentRecord) -> dict[str, Any]:
    """Send a notification for a routed document.

    Returns a dict with the notification result (always succeeds —
    webhook failures are logged, not raised).
    """
    routing = record.routing
    assert routing is not None, "Document must be routed before notification"

    payload = {
        "document_id": str(record.id),
        "content_hash": record.content_hash,
        "filename": record.filename,
        "document_type": record.document_type.value,
        "queue": routing.queue,
        "urgency": routing.urgency.value,
        "reason": routing.reason,
        "status": record.status.value,
    }

    # Always log
    logger.info(
        "NOTIFY → queue=%s urgency=%s doc=%s reason=%s",
        routing.queue,
        routing.urgency.value,
        record.filename or record.content_hash[:12],
        routing.reason,
    )

    # Optionally POST to webhook
    settings = get_settings()
    webhook_url = settings.notify_webhook_url
    if webhook_url:
        try:
            import httpx

            resp = httpx.post(webhook_url, json=payload, timeout=10.0)
            logger.info("Webhook notification sent: %s → %d", webhook_url, resp.status_code)
            payload["webhook_status"] = resp.status_code
        except Exception as exc:
            logger.warning("Webhook notification failed: %s", exc)
            payload["webhook_error"] = str(exc)
    else:
        payload["webhook_status"] = "skipped (no URL configured)"

    return payload
