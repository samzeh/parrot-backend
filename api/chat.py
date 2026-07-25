"""Chat + health FastAPI routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.polly import handle_message
from services.linq import is_configured as linq_is_configured

router = APIRouter(tags=["polly"])


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Stable user identifier")
    message: str = Field(..., min_length=1)
    phone: str | None = None


class ChatResponse(BaseModel):
    user_id: str
    reply: str


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "polly",
        "linq_configured": linq_is_configured(),
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """Local/dev endpoint — talk to Polly without Linq."""
    reply = handle_message(body.user_id, body.message, phone=body.phone)
    return ChatResponse(user_id=body.user_id, reply=reply)
