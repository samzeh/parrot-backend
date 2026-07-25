"""In-memory conversation history for Polly.

For the prototype this is enough — history lives for the life of the process.
Swap to Supabase/Postgres later only if you need persistence across restarts.
"""

from __future__ import annotations

from collections import defaultdict

# user_id -> list of {role, content}
_history: dict[str, list[dict[str, str]]] = defaultdict(list)


def get_history(user_id: str, limit: int = 20) -> list[dict[str, str]]:
    messages = _history[user_id]
    return list(messages[-limit:])


def append_message(user_id: str, role: str, content: str) -> None:
    _history[user_id].append({"role": role, "content": content})


def clear_history(user_id: str | None = None) -> None:
    if user_id is None:
        _history.clear()
    else:
        _history.pop(user_id, None)
