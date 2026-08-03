"""Conversation history for the single test user (data/user.json)."""

from __future__ import annotations

from typing import Any

from services import json_store


def get_history(_user_id: str | None = None, limit: int = 20) -> list[dict[str, str]]:
    store = json_store.load()
    messages: list[dict[str, Any]] = store.get("messages", [])
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-limit:]
    ]


def append_message(_user_id: str | None = None, role: str = "", content: str = "") -> None:
    store = json_store.load()
    store.setdefault("messages", []).append({"role": role, "content": content})
    json_store.save(store)


def clear_history(_user_id: str | None = None) -> None:
    store = json_store.load()
    store["messages"] = []
    json_store.save(store)
