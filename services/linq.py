"""Linq messaging API client — send replies back to users."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

LINQ_API_BASE = os.getenv(
    "LINQ_API_BASE",
    "https://api.linqapp.com/api/partner/v3",
)


class LinqError(RuntimeError):
    pass


def _api_key() -> str | None:
    return os.getenv("LINQ_API_KEY") or os.getenv("LINQ_API_V3_API_KEY")


def is_configured() -> bool:
    return bool(_api_key())


def verify_webhook_signature(
    body: bytes,
    *,
    webhook_id: str | None,
    webhook_timestamp: str | None,
    webhook_signature: str | None,
) -> bool:
    """Verify Standard Webhooks signature (Linq v3).

    If LINQ_WEBHOOK_SECRET is unset, verification is skipped (local/dev).
    """
    secret = os.getenv("LINQ_WEBHOOK_SECRET")
    if not secret:
        logger.warning("LINQ_WEBHOOK_SECRET unset — skipping signature verification")
        return True

    if not webhook_id or not webhook_timestamp or not webhook_signature:
        return False

    # Secret may be provided as "whsec_<base64>" (Standard Webhooks) or raw.
    key = secret
    if secret.startswith("whsec_"):
        import base64

        key_bytes = base64.b64decode(secret[len("whsec_") :])
    else:
        key_bytes = secret.encode("utf-8")

    signed_content = f"{webhook_id}.{webhook_timestamp}.{body.decode('utf-8')}"
    digest = hmac.new(
        key_bytes,
        signed_content.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    import base64

    expected = "v1," + base64.b64encode(digest).decode("utf-8")
    # Header may contain multiple space-delimited signatures.
    candidates = [part.strip() for part in webhook_signature.split(" ")]
    return any(hmac.compare_digest(expected, candidate) for candidate in candidates)


def extract_inbound_text(payload: dict[str, Any]) -> dict[str, str | None] | None:
    """Parse a Linq message.received webhook into chat/user/text fields.

    Supports the 2026-02-03 MessageEventV2 shape.
    """
    event_type = payload.get("event_type") or payload.get("type")
    data = payload.get("data") or {}

    # Ignore non-inbound / non-message events.
    if event_type and event_type not in {"message.received", "message.created"}:
        # Still allow payloads that omit event_type but look inbound.
        if data.get("direction") != "inbound":
            return None

    direction = data.get("direction")
    if direction and direction != "inbound":
        return None

    chat = data.get("chat") or {}
    chat_id = chat.get("id") or data.get("chat_id")

    sender = data.get("sender_handle") or {}
    phone = sender.get("handle") or data.get("sender") or data.get("from")

    parts = data.get("parts")
    if parts is None:
        message = data.get("message") or {}
        parts = message.get("parts") or []

    text_chunks: list[str] = []
    for part in parts or []:
        if isinstance(part, dict) and part.get("type") == "text":
            value = part.get("value") or part.get("text") or ""
            if value:
                text_chunks.append(str(value))

    text = "\n".join(text_chunks).strip()
    if not text or not chat_id:
        return None

    return {
        "chat_id": str(chat_id),
        "phone": str(phone) if phone else None,
        "text": text,
        "message_id": str(data.get("id")) if data.get("id") else None,
    }


async def send_chat_message(chat_id: str, text: str) -> dict[str, Any]:
    """Send a text reply into an existing Linq chat."""
    api_key = _api_key()
    if not api_key:
        raise LinqError("LINQ_API_KEY is not set — cannot send outbound message.")

    url = f"{LINQ_API_BASE}/chats/{chat_id}/messages"
    payload = {
        "message": {
            "parts": [
                {"type": "text", "value": text},
            ]
        }
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            logger.error(
                "Linq send failed (%s): %s",
                response.status_code,
                response.text,
            )
            raise LinqError(
                f"Linq API error {response.status_code}: {response.text[:300]}"
            )
        return response.json()
