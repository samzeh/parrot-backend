"""Mock Parrot data for the single test user in data/user.json.

No user creation — the JSON file is the source of truth. Polly only updates it.
user_id arguments are ignored (kept for API shape compatibility).
"""

from __future__ import annotations

import copy
import random
from datetime import datetime, timezone
from typing import Any

from services import json_store

# Fixed test learner — everything maps to this one JSON record.
TEST_USER_ID = "test"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_user(_user_id: str | None = None) -> dict[str, Any]:
    return copy.deepcopy(json_store.load()["profile"])


def update_user(
    _user_id: str | None = None,
    *,
    display_name: str | None = None,
    spanish_level: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    store = json_store.load()
    profile = store["profile"]
    if display_name:
        profile["display_name"] = display_name
    if spanish_level:
        profile["spanish_level"] = spanish_level.strip().lower()
    if phone:
        profile["phone"] = phone
    json_store.save(store)
    return copy.deepcopy(profile)


def get_progress(_user_id: str | None = None) -> dict[str, Any]:
    store = json_store.load()
    progress = store["progress"]
    return {
        "user_id": store["profile"].get("user_id", TEST_USER_ID),
        "display_name": store["profile"]["display_name"],
        "spanish_level": store["profile"]["spanish_level"],
        "words_saved": len(store["dictionary"]),
        "words_known": progress["words_known"],
        "words_learning": progress["words_learning"],
        "streak_days": progress["streak_days"],
        "total_practice_minutes": progress["total_practice_minutes"],
        "last_practice_at": progress["last_practice_at"],
    }


def get_dictionary(_user_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    store = json_store.load()
    words = list(reversed(store["dictionary"]))[:limit]
    return {
        "user_id": store["profile"].get("user_id", TEST_USER_ID),
        "count": len(words),
        "words": copy.deepcopy(words),
    }


def save_word(
    _user_id: str | None = None,
    word: str = "",
    translation: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    cleaned = word.strip().lower()
    if not cleaned:
        return {"ok": False, "error": "Word cannot be empty."}

    store = json_store.load()
    for entry in store["dictionary"]:
        if entry["word"] == cleaned:
            return {
                "ok": True,
                "already_saved": True,
                "word": cleaned,
                "translation": entry.get("translation"),
                "message": f'"{cleaned}" is already in your dictionary.',
            }

    lookup = store.get("word_bank", {}).get(cleaned)
    resolved = translation or (lookup.get("translation") if lookup else None)
    entry = {
        "word": cleaned,
        "translation": resolved,
        "notes": notes,
        "created_at": _utc_now(),
    }
    store["dictionary"].append(entry)
    store["progress"]["words_learning"] = int(store["progress"].get("words_learning", 0)) + 1
    store["progress"]["words_known"] = int(store["progress"].get("words_known", 0)) + 1
    json_store.save(store)

    return {
        "ok": True,
        "already_saved": False,
        "word": cleaned,
        "translation": resolved,
        "message": f'Saved "{cleaned}"'
        + (f" ({resolved})" if resolved else "")
        + ".",
    }


def lookup_word(word: str) -> dict[str, Any]:
    cleaned = word.strip().lower()
    store = json_store.load()
    entry = store.get("word_bank", {}).get(cleaned)
    if not entry:
        return {
            "ok": False,
            "word": cleaned,
            "found": False,
            "message": f'No dictionary entry for "{cleaned}" yet. You can still save it.',
        }
    return {"ok": True, "word": cleaned, "found": True, **entry}


def start_practice(_user_id: str | None = None, focus: str | None = None) -> dict[str, Any]:
    store = json_store.load()
    now = _utc_now()

    for session in store["sessions"]:
        if session.get("status") == "active":
            session["status"] = "ended"
            session["ended_at"] = now

    store["session_counter"] = int(store.get("session_counter", 0)) + 1
    session_id = store["session_counter"]

    vocab = store["dictionary"]
    practice_words = (
        copy.deepcopy(random.sample(vocab, min(5, len(vocab))))
        if vocab
        else [{"word": "hola", "translation": "hello"}]
    )
    practice_words = [
        {"word": w["word"], "translation": w.get("translation")} for w in practice_words
    ]

    session = {
        "session_id": session_id,
        "user_id": store["profile"].get("user_id", TEST_USER_ID),
        "status": "active",
        "focus": focus or "general conversation",
        "started_at": now,
        "ended_at": None,
        "practice_words": practice_words,
    }
    store["sessions"].append(session)
    store["progress"]["streak_days"] = int(store["progress"].get("streak_days", 0)) + 1
    store["progress"]["last_practice_at"] = now
    store["progress"]["total_practice_minutes"] = (
        int(store["progress"].get("total_practice_minutes", 0)) + 5
    )
    json_store.save(store)

    return {
        "ok": True,
        "session_id": session_id,
        "focus": session["focus"],
        "started_at": now,
        "practice_words": practice_words,
        "prompt": (
            "Start a short practice chat using these words. "
            "Keep prompts easy and encourage the learner."
        ),
    }


# Back-compat alias used by older call sites / tests
def ensure_user(_user_id: str | None = None, **_kwargs: Any) -> dict[str, Any]:
    return get_user()


def reset_all() -> None:
    """Clear chat + practice history on the test user (keeps dictionary/profile)."""
    store = json_store.load()
    store["messages"] = []
    store["sessions"] = []
    store["session_counter"] = 0
    json_store.save(store)
