"""Linq webhook FastAPI routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from agent.polly import handle_message
from services.linq import (
    extract_inbound_text,
    is_configured as linq_is_configured,
    send_chat_message,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["linq"])


async def _process_linq_inbound(chat_id: str, phone: str | None, text: str) -> None:
    user_id = phone or f"chat:{chat_id}"
    try:
        reply = handle_message(user_id, text, phone=phone)
        if linq_is_configured():
            await send_chat_message(chat_id, reply)
        else:
            logger.warning(
                "LINQ_API_KEY missing — generated reply but did not send. reply=%r",
                reply,
            )
    except Exception:
        logger.exception("Failed processing Linq inbound for chat %s", chat_id)


async def _handle_linq_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    webhook_id: str | None,
    webhook_timestamp: str | None,
    webhook_signature: str | None,
) -> dict[str, str]:
    body = await request.body()

    if not verify_webhook_signature(
        body,
        webhook_id=webhook_id,
        webhook_timestamp=webhook_timestamp,
        webhook_signature=webhook_signature,
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    event_type = payload.get("event_type") or payload.get("type")
    logger.info("Linq webhook received: %s", event_type)

    inbound = extract_inbound_text(payload)
    if not inbound:
        return {"status": "ignored"}

    background_tasks.add_task(
        _process_linq_inbound,
        inbound["chat_id"],
        inbound.get("phone"),
        inbound["text"],
    )
    return {"status": "accepted"}


@router.post("/webhook/linq")
async def linq_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    webhook_id: str | None = Header(default=None, alias="webhook-id"),
    webhook_timestamp: str | None = Header(default=None, alias="webhook-timestamp"),
    webhook_signature: str | None = Header(default=None, alias="webhook-signature"),
) -> dict[str, str]:
    """Receive Linq webhook events (subscribe to message.received)."""
    return await _handle_linq_webhook(
        request,
        background_tasks,
        webhook_id,
        webhook_timestamp,
        webhook_signature,
    )


@router.post("/linq/webhook")
async def linq_webhook_alias(
    request: Request,
    background_tasks: BackgroundTasks,
    webhook_id: str | None = Header(default=None, alias="webhook-id"),
    webhook_timestamp: str | None = Header(default=None, alias="webhook-timestamp"),
    webhook_signature: str | None = Header(default=None, alias="webhook-signature"),
) -> dict[str, str]:
    return await _handle_linq_webhook(
        request,
        background_tasks,
        webhook_id,
        webhook_timestamp,
        webhook_signature,
    )
