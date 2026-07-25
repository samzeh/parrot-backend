"""Client Polly tools use for Parrot data.

Calls the in-memory store directly (same functions the FastAPI /api routes use).
HTTP endpoints in api/mock_parrot.py remain for curl/docs and future real Parrot APIs.
"""

from __future__ import annotations

from typing import Any

from services import parrot_data


def get_user_profile(user_id: str) -> dict[str, Any]:
    return parrot_data.get_user(user_id)


def get_learning_progress(user_id: str) -> dict[str, Any]:
    return parrot_data.get_progress(user_id)


def get_learning_words(user_id: str, limit: int = 20) -> dict[str, Any]:
    return parrot_data.get_dictionary(user_id, limit=limit)


def save_word(
    user_id: str,
    word: str,
    translation: str | None = None,
) -> dict[str, Any]:
    return parrot_data.save_word(user_id, word, translation=translation)


def lookup_word(word: str) -> dict[str, Any]:
    return parrot_data.lookup_word(word)


def start_practice_session(
    user_id: str,
    focus: str | None = None,
) -> dict[str, Any]:
    return parrot_data.start_practice(user_id, focus=focus)
