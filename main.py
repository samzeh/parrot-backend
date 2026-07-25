"""FastAPI application — all HTTP endpoints live on routers under api/."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from api.chat import router as chat_router
from api.mock_parrot import router as mock_parrot_router
from api.webhooks import router as webhooks_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(
    title="Polly — Parrot Spanish Companion",
    description="Messaging-first AI Spanish tutor backed by Gemini + mock Parrot APIs.",
    version="0.1.0",
)

app.include_router(chat_router)
app.include_router(webhooks_router)
app.include_router(mock_parrot_router)
