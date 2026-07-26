"""Phone verification codes — generate, deliver over Linq, and validate.

Codes live in memory for the life of the process, which is enough for the
prototype. Swap `_records` for Redis/Postgres when you need multi-worker or
restart-safe behaviour; nothing outside this module depends on the storage.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field

from services import linq

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_TTL_SECONDS = 10 * 60
"""How long a delivered code stays valid."""

MAX_VERIFY_ATTEMPTS = 5
"""Wrong guesses allowed per issued code before it is burned."""

RESEND_COOLDOWN_SECONDS = 30
"""Minimum gap between two sends to the same number."""

SEND_WINDOW_SECONDS = 15 * 60
MAX_SENDS_PER_WINDOW = 5
"""Sends allowed per number inside SEND_WINDOW_SECONDS."""

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

_lock = asyncio.Lock()


class VerificationError(RuntimeError):
    """Base class for expected, user-facing verification failures."""


class InvalidPhoneError(VerificationError):
    pass


class RateLimitedError(VerificationError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many verification codes requested.")
        self.retry_after = retry_after


class DeliveryError(VerificationError):
    pass


@dataclass
class _Record:
    code_hash: str
    salt: str
    expires_at: float
    attempts: int = 0
    last_sent_at: float = 0.0
    send_times: list[float] = field(default_factory=list)
    verified_at: float | None = None


_records: dict[str, _Record] = {}


def normalize_phone(raw: str) -> str:
    """Accept human-entered numbers, return E.164 or raise InvalidPhoneError."""
    if not raw:
        raise InvalidPhoneError("Phone number is required.")

    cleaned = re.sub(r"[\s()\-.]", "", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        # Bare 10-digit input is assumed to be US/Canada, matching the app's default.
        digits = re.sub(r"\D", "", cleaned)
        cleaned = "+1" + digits if len(digits) == 10 else "+" + digits

    if not E164_RE.match(cleaned):
        raise InvalidPhoneError(f"'{raw}' is not a valid phone number.")
    return cleaned


def _hash_code(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def _message_body(code: str) -> str:
    return (
        f"Your Parrot verification code is {code}. "
        f"It expires in {CODE_TTL_SECONDS // 60} minutes."
    )


def _prune(now: float) -> None:
    stale = [
        phone
        for phone, record in _records.items()
        if record.expires_at < now
        and (not record.send_times or record.send_times[-1] + SEND_WINDOW_SECONDS < now)
    ]
    for phone in stale:
        _records.pop(phone, None)


def _check_rate_limit(record: _Record | None, now: float) -> None:
    if record is None:
        return

    since_last = now - record.last_sent_at
    if record.last_sent_at and since_last < RESEND_COOLDOWN_SECONDS:
        raise RateLimitedError(int(RESEND_COOLDOWN_SECONDS - since_last) + 1)

    recent = [t for t in record.send_times if now - t < SEND_WINDOW_SECONDS]
    record.send_times = recent
    if len(recent) >= MAX_SENDS_PER_WINDOW:
        oldest = min(recent)
        raise RateLimitedError(int(SEND_WINDOW_SECONDS - (now - oldest)) + 1)


async def send_code(phone: str) -> dict[str, object]:
    """Issue a fresh code for `phone` and deliver it over iMessage.

    This is the single delivery path — the resend endpoint calls straight into it
    so both flows share generation, storage, and rate limiting.
    """
    e164 = normalize_phone(phone)
    now = time.time()

    async with _lock:
        _prune(now)
        record = _records.get(e164)
        _check_rate_limit(record, now)

        code = _generate_code()
        salt = secrets.token_hex(8)
        history = list(record.send_times) if record else []
        _records[e164] = _Record(
            code_hash=_hash_code(code, salt),
            salt=salt,
            expires_at=now + CODE_TTL_SECONDS,
            last_sent_at=now,
            send_times=history + [now],
        )

    if not linq.can_send_outbound():
        # Dev fallback: without credentials there is no way to receive the code.
        logger.warning(
            "Linq not configured (need LINQ_API_KEY + LINQ_FROM_NUMBER) — "
            "verification code for %s was not sent. code=%s",
            e164,
            code,
        )
        return {
            "phone": e164,
            "delivered": False,
            "expires_in": CODE_TTL_SECONDS,
            "resend_available_in": RESEND_COOLDOWN_SECONDS,
        }

    try:
        result = await linq.send_text_to_number(
            e164,
            _message_body(code),
            preferred_service=os.getenv("LINQ_PREFERRED_SERVICE") or None,
        )
    except linq.LinqError as exc:
        async with _lock:
            # Failed delivery shouldn't consume the caller's resend budget.
            stored = _records.get(e164)
            if stored:
                stored.send_times = [t for t in stored.send_times if t != now]
                stored.last_sent_at = 0.0
        if exc.status_code == 429:
            raise RateLimitedError(RESEND_COOLDOWN_SECONDS) from exc
        raise DeliveryError(str(exc)) from exc

    logger.info("Verification code sent to %s (chat=%s)", e164, result.get("id"))
    return {
        "phone": e164,
        "delivered": True,
        "expires_in": CODE_TTL_SECONDS,
        "resend_available_in": RESEND_COOLDOWN_SECONDS,
    }


async def resend_code(phone: str) -> dict[str, object]:
    """Send a brand-new code, reusing the same delivery + rate-limit path."""
    return await send_code(phone)


async def verify_code(phone: str, code: str) -> dict[str, object]:
    e164 = normalize_phone(phone)
    submitted = re.sub(r"\D", "", code or "")
    now = time.time()

    async with _lock:
        record = _records.get(e164)
        if record is None:
            return {"verified": False, "reason": "no_code", "phone": e164}
        if record.expires_at < now:
            _records.pop(e164, None)
            return {"verified": False, "reason": "expired", "phone": e164}
        if record.attempts >= MAX_VERIFY_ATTEMPTS:
            return {"verified": False, "reason": "too_many_attempts", "phone": e164}

        if not hmac.compare_digest(
            record.code_hash, _hash_code(submitted, record.salt)
        ):
            record.attempts += 1
            remaining = MAX_VERIFY_ATTEMPTS - record.attempts
            return {
                "verified": False,
                "reason": "invalid_code",
                "attempts_remaining": max(remaining, 0),
                "phone": e164,
            }

        record.verified_at = now
        # Burn the code so it can't be replayed.
        record.code_hash = ""
        return {"verified": True, "phone": e164}


def is_verified(phone: str) -> bool:
    record = _records.get(normalize_phone(phone))
    return bool(record and record.verified_at)


def reset() -> None:
    """Test helper — drop all issued codes."""
    _records.clear()
