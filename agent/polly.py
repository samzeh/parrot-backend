"""Polly — conversational Spanish tutor agent."""

from __future__ import annotations

import logging

from agent.prompts import POLLY_SYSTEM_PROMPT, build_user_context
from agent.tools import build_tools_for_user
from services import memory, parrot_client, parrot_data
from services.gemini import GeminiError, generate_with_tools
from services.parrot_data import TEST_USER_ID

logger = logging.getLogger(__name__)


def handle_message(_user_id: str | None, message: str, *, phone: str | None = None) -> str:
    """Process one message for the single test learner in data/user.json."""
    cleaned = (message or "").strip()
    if not cleaned:
        return "I didn't catch that — send me a message and I'll help you learn Spanish!"

    user_id = TEST_USER_ID
    if phone:
        parrot_data.update_user(user_id, phone=phone)

    profile = parrot_client.get_user_profile(user_id)
    recent = parrot_client.get_learning_words(user_id, limit=8).get("words", [])
    context = build_user_context(profile, recent_words=recent)
    system_instruction = f"{POLLY_SYSTEM_PROMPT}\n\nCurrent learner context:\n{context}"

    history = memory.get_history(user_id, limit=16)
    tools = build_tools_for_user(user_id)

    try:
        reply = generate_with_tools(
            system_instruction=system_instruction,
            history=history,
            user_message=cleaned,
            tools=tools,
        )
    except GeminiError as exc:
        logger.exception("Gemini error for user %s: %s", user_id, exc)
        reply = str(exc)
    except Exception:
        logger.exception("Unexpected Polly error for user %s", user_id)
        reply = "Oops — something went wrong on my side. Mind sending that again?"

    memory.append_message(user_id, "user", cleaned)
    memory.append_message(user_id, "assistant", reply)
    return reply
