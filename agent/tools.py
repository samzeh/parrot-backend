"""Agent tools Polly can call. Bound per-user for Gemini automatic function calling."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from services import parrot_client


ToolFunc = Callable[..., Any]


def build_tools_for_user(user_id: str) -> list[ToolFunc]:
    """Return Python callables Gemini can invoke automatically for this user."""

    def get_learning_progress() -> dict[str, Any]:
        """Get the user's Spanish learning progress, streak, and word counts."""
        return parrot_client.get_learning_progress(user_id)

    def save_word(word: str, translation: str | None = None) -> dict[str, Any]:
        """Save a Spanish word to the user's vocabulary / dictionary.

        Args:
            word: The Spanish word to save.
            translation: Optional English translation.
        """
        return parrot_client.save_word(user_id, word, translation=translation)

    def get_learning_words(limit: int = 20) -> dict[str, Any]:
        """List Spanish words in the user's dictionary.

        Args:
            limit: Maximum number of words to return (default 20).
        """
        return parrot_client.get_learning_words(user_id, limit=limit)

    def lookup_word(word: str) -> dict[str, Any]:
        """Look up a Spanish word's meaning, part of speech, and example sentence.

        Args:
            word: The Spanish word to look up.
        """
        return parrot_client.lookup_word(word)

    def start_practice_session(focus: str | None = None) -> dict[str, Any]:
        """Start a short Spanish practice session for the user.

        Args:
            focus: Optional focus topic, e.g. 'greetings' or 'food vocabulary'.
        """
        return parrot_client.start_practice_session(user_id, focus=focus)

    return [
        get_learning_progress,
        save_word,
        get_learning_words,
        lookup_word,
        start_practice_session,
    ]
