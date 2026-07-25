"""Mock Parrot FastAPI endpoints.

Stand-in for the real Parrot backend. Polly tools call these over HTTP/ASGI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import parrot_data

router = APIRouter(prefix="/api", tags=["mock-parrot"])


class SaveWordRequest(BaseModel):
    word: str = Field(..., min_length=1)
    translation: str | None = None
    notes: str | None = None


class PracticeRequest(BaseModel):
    focus: str | None = None


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    spanish_level: str | None = None
    phone: str | None = None


@router.get("/users/{user_id}")
async def get_user(user_id: str) -> dict[str, Any]:
    """Get a user profile."""
    return parrot_data.get_user(user_id)


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest) -> dict[str, Any]:
    """Update basic user fields (mock)."""
    if body.spanish_level:
        level = body.spanish_level.strip().lower()
        allowed = {"beginner", "elementary", "intermediate", "advanced"}
        if level not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"spanish_level must be one of: {', '.join(sorted(allowed))}",
            )
        body.spanish_level = level

    return parrot_data.update_user(
        user_id,
        display_name=body.display_name,
        spanish_level=body.spanish_level,
        phone=body.phone,
    )


@router.get("/users/{user_id}/progress")
async def get_progress(user_id: str) -> dict[str, Any]:
    """Get learning progress for a user."""
    return parrot_data.get_progress(user_id)


@router.get("/users/{user_id}/dictionary")
async def get_dictionary(user_id: str, limit: int = 50) -> dict[str, Any]:
    """Get the user's saved Spanish dictionary / vocabulary."""
    return parrot_data.get_dictionary(user_id, limit=limit)


@router.post("/users/{user_id}/dictionary")
async def save_word(user_id: str, body: SaveWordRequest) -> dict[str, Any]:
    """Save a word to the user's dictionary."""
    result = parrot_data.save_word(
        user_id,
        body.word,
        translation=body.translation,
        notes=body.notes,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Bad request"))
    return result


@router.get("/dictionary/{word}")
async def lookup_word(word: str) -> dict[str, Any]:
    """Look up a Spanish word in the global dictionary."""
    return parrot_data.lookup_word(word)


@router.post("/users/{user_id}/practice")
async def start_practice(
    user_id: str,
    body: PracticeRequest | None = None,
) -> dict[str, Any]:
    """Start a practice session for the user."""
    focus = body.focus if body else None
    return parrot_data.start_practice(user_id, focus=focus)
