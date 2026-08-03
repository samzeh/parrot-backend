"""JSON file persistence for the single test user.

Prototype stores one learner in data/user.json. Polly always reads/writes
that file — no multi-user creation.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=True)

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "user.json"
DATA_PATH = Path(os.getenv("USER_DATA_PATH", str(_DEFAULT_PATH)))

_lock = threading.Lock()


def _ensure_parent() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def load() -> dict[str, Any]:
    """Load the test user file. Always fresh from disk."""
    with _lock:
        if not DATA_PATH.exists():
            raise FileNotFoundError(
                f"Test user file not found at {DATA_PATH}. "
                "Create data/user.json before talking to Polly."
            )
        try:
            with DATA_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Could not read {DATA_PATH}: {exc}") from exc

        if not isinstance(data, dict) or "profile" not in data:
            raise ValueError(f"{DATA_PATH} must be a JSON object with a 'profile' field.")

        data.setdefault("session_counter", 0)
        data.setdefault("word_bank", {})
        data.setdefault("dictionary", [])
        data.setdefault("progress", {})
        data.setdefault("sessions", [])
        data.setdefault("messages", [])
        return data


def save(data: dict[str, Any]) -> None:
    """Overwrite the JSON file."""
    with _lock:
        _ensure_parent()
        tmp = DATA_PATH.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        tmp.replace(DATA_PATH)
