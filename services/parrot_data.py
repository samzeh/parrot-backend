"""In-memory Parrot data store for the prototype.

No database needed for MVP — this fakes what the real Parrot backend
will eventually return. Data resets when the server restarts.
"""

from __future__ import annotations

import copy
import random
from datetime import datetime, timezone
from typing import Any


DICTIONARY: dict[str, dict[str, str]] = {
    "perro": {
        "translation": "dog",
        "part_of_speech": "noun",
        "example_es": "El perro corre en el parque.",
        "example_en": "The dog runs in the park.",
    },
    "gato": {
        "translation": "cat",
        "part_of_speech": "noun",
        "example_es": "El gato duerme en el sofá.",
        "example_en": "The cat sleeps on the sofa.",
    },
    "casa": {
        "translation": "house",
        "part_of_speech": "noun",
        "example_es": "Mi casa es pequeña.",
        "example_en": "My house is small.",
    },
    "comer": {
        "translation": "to eat",
        "part_of_speech": "verb",
        "example_es": "Me gusta comer fruta.",
        "example_en": "I like to eat fruit.",
    },
    "hablar": {
        "translation": "to speak",
        "part_of_speech": "verb",
        "example_es": "Quiero hablar español.",
        "example_en": "I want to speak Spanish.",
    },
    "hola": {
        "translation": "hello",
        "part_of_speech": "interjection",
        "example_es": "¡Hola! ¿Cómo estás?",
        "example_en": "Hello! How are you?",
    },
    "gracias": {
        "translation": "thank you",
        "part_of_speech": "interjection",
        "example_es": "¡Muchas gracias!",
        "example_en": "Thank you very much!",
    },
}

_SEED_WORDS = [
    {"word": "hola", "translation": "hello"},
    {"word": "gracias", "translation": "thank you"},
    {"word": "agua", "translation": "water"},
    {"word": "amigo", "translation": "friend"},
    {"word": "aprender", "translation": "to learn"},
]

# user_id -> user record
_users: dict[str, dict[str, Any]] = {}
# user_id -> list of vocab entries
_dictionaries: dict[str, list[dict[str, Any]]] = {}
# user_id -> progress stats
_progress: dict[str, dict[str, Any]] = {}
# user_id -> practice sessions
_sessions: dict[str, list[dict[str, Any]]] = {}
_session_counter = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_user(
    user_id: str,
    *,
    display_name: str = "Learner",
    spanish_level: str = "beginner",
    phone: str | None = None,
) -> dict[str, Any]:
    if user_id not in _users:
        now = _utc_now()
        _users[user_id] = {
            "user_id": user_id,
            "display_name": display_name,
            "spanish_level": spanish_level,
            "phone": phone,
            "created_at": now,
        }
        _dictionaries[user_id] = [
            {**w, "notes": None, "created_at": now} for w in _SEED_WORDS
        ]
        _progress[user_id] = {
            "words_known": 12,
            "words_learning": 5,
            "streak_days": 3,
            "total_practice_minutes": 45,
            "last_practice_at": None,
        }
        _sessions[user_id] = []
    elif phone and _users[user_id].get("phone") != phone:
        _users[user_id]["phone"] = phone

    return copy.deepcopy(_users[user_id])


def get_user(user_id: str) -> dict[str, Any]:
    return ensure_user(user_id)


def update_user(
    user_id: str,
    *,
    display_name: str | None = None,
    spanish_level: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    ensure_user(user_id, phone=phone)
    if display_name:
        _users[user_id]["display_name"] = display_name
    if spanish_level:
        _users[user_id]["spanish_level"] = spanish_level.strip().lower()
    if phone:
        _users[user_id]["phone"] = phone
    return get_user(user_id)


def get_progress(user_id: str) -> dict[str, Any]:
    user = ensure_user(user_id)
    progress = _progress[user_id]
    return {
        "user_id": user_id,
        "display_name": user["display_name"],
        "spanish_level": user["spanish_level"],
        "words_saved": len(_dictionaries[user_id]),
        "words_known": progress["words_known"],
        "words_learning": progress["words_learning"],
        "streak_days": progress["streak_days"],
        "total_practice_minutes": progress["total_practice_minutes"],
        "last_practice_at": progress["last_practice_at"],
    }


def get_dictionary(user_id: str, limit: int = 50) -> dict[str, Any]:
    ensure_user(user_id)
    words = list(reversed(_dictionaries[user_id]))[:limit]
    return {
        "user_id": user_id,
        "count": len(words),
        "words": copy.deepcopy(words),
    }


def save_word(
    user_id: str,
    word: str,
    translation: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    ensure_user(user_id)
    cleaned = word.strip().lower()
    if not cleaned:
        return {"ok": False, "error": "Word cannot be empty."}

    for entry in _dictionaries[user_id]:
        if entry["word"] == cleaned:
            return {
                "ok": True,
                "already_saved": True,
                "word": cleaned,
                "translation": entry.get("translation"),
                "message": f'"{cleaned}" is already in your dictionary.',
            }

    lookup = DICTIONARY.get(cleaned)
    resolved = translation or (lookup["translation"] if lookup else None)
    entry = {
        "word": cleaned,
        "translation": resolved,
        "notes": notes,
        "created_at": _utc_now(),
    }
    _dictionaries[user_id].append(entry)
    _progress[user_id]["words_learning"] += 1
    _progress[user_id]["words_known"] += 1

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
    entry = DICTIONARY.get(cleaned)
    if not entry:
        return {
            "ok": False,
            "word": cleaned,
            "found": False,
            "message": f'No dictionary entry for "{cleaned}" yet. You can still save it.',
        }
    return {"ok": True, "word": cleaned, "found": True, **entry}


def start_practice(user_id: str, focus: str | None = None) -> dict[str, Any]:
    global _session_counter
    ensure_user(user_id)
    now = _utc_now()

    for session in _sessions[user_id]:
        if session["status"] == "active":
            session["status"] = "ended"
            session["ended_at"] = now

    _session_counter += 1
    vocab = _dictionaries[user_id]
    practice_words = (
        copy.deepcopy(random.sample(vocab, min(5, len(vocab))))
        if vocab
        else [{"word": "hola", "translation": "hello"}]
    )
    # Strip notes/created_at for practice payload
    practice_words = [
        {"word": w["word"], "translation": w.get("translation")} for w in practice_words
    ]

    session = {
        "session_id": _session_counter,
        "user_id": user_id,
        "status": "active",
        "focus": focus or "general conversation",
        "started_at": now,
        "ended_at": None,
        "practice_words": practice_words,
    }
    _sessions[user_id].append(session)

    _progress[user_id]["streak_days"] += 1
    _progress[user_id]["last_practice_at"] = now
    _progress[user_id]["total_practice_minutes"] += 5

    return {
        "ok": True,
        "session_id": session["session_id"],
        "focus": session["focus"],
        "started_at": now,
        "practice_words": practice_words,
        "prompt": (
            "Start a short practice chat using these words. "
            "Keep prompts easy and encourage the learner."
        ),
    }


def reset_all() -> None:
    """Clear all in-memory state (useful for tests)."""
    global _session_counter
    _users.clear()
    _dictionaries.clear()
    _progress.clear()
    _sessions.clear()
    _session_counter = 0
