r"""Exercise the verification service without sending real iMessages.

Linq delivery is stubbed so the code can be read back and asserted against.
Run from the repo root:  venv\Scripts\python.exe scripts\test_verification.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import linq, verification  # noqa: E402

PHONE = "+15555550123"

sent: list[str] = []


async def _fake_send(phone: str, text: str, **_: object) -> dict[str, object]:
    sent.append(text)
    return {"id": "chat_test"}


def _code_from_last_message() -> str:
    match = re.search(r"\b(\d{6})\b", sent[-1])
    assert match, f"no code in message: {sent[-1]!r}"
    return match.group(1)


def _allow_resend_now() -> None:
    """Rewind the cooldown so the next send is permitted."""
    record = verification._records[PHONE]
    record.last_sent_at = 0.0
    record.send_times = []


def check(label: str, condition: bool, detail: object = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(1)


async def main() -> None:
    linq.send_text_to_number = _fake_send  # type: ignore[assignment]
    linq.can_send_outbound = lambda: True  # type: ignore[assignment]

    check(
        "normalize 10-digit US input",
        verification.normalize_phone("(205) 490-9406") == "+12054909406",
    )
    check(
        "normalize already-E.164",
        verification.normalize_phone("+1 205 490 9406") == "+12054909406",
    )
    try:
        verification.normalize_phone("12")
        check("reject short number", False)
    except verification.InvalidPhoneError:
        check("reject short number", True)

    verification.reset()

    result = await verification.verify_code(PHONE, "000000")
    check("verify with no code issued", result["reason"] == "no_code", result)

    send = await verification.send_code(PHONE)
    code = _code_from_last_message()
    check("send delivers a 6-digit code", send["delivered"] and len(code) == 6, code)

    wrong = await verification.verify_code(PHONE, "999999" if code != "999999" else "111111")
    check(
        "wrong code decrements attempts",
        wrong["verified"] is False and wrong["attempts_remaining"] == 4,
        wrong,
    )

    ok = await verification.verify_code(PHONE, code)
    check("correct code verifies", ok["verified"] is True, ok)
    check("is_verified reflects success", verification.is_verified(PHONE))

    replay = await verification.verify_code(PHONE, code)
    check("code cannot be replayed", replay["verified"] is False, replay)

    # --- rate limiting ---
    verification.reset()
    await verification.send_code(PHONE)
    try:
        await verification.send_code(PHONE)
        check("resend cooldown enforced", False)
    except verification.RateLimitedError as exc:
        check("resend cooldown enforced", exc.retry_after > 0, f"retry_after={exc.retry_after}s")

    for index in range(verification.MAX_SENDS_PER_WINDOW - 1):
        _allow_resend_now()
        await verification.resend_code(PHONE)
    _allow_resend_now()
    verification._records[PHONE].send_times = [
        verification.time.time() for _ in range(verification.MAX_SENDS_PER_WINDOW)
    ]
    try:
        await verification.resend_code(PHONE)
        check("window send cap enforced", False)
    except verification.RateLimitedError as exc:
        check("window send cap enforced", exc.retry_after > 0, f"retry_after={exc.retry_after}s")

    # --- expiry ---
    verification.reset()
    await verification.send_code(PHONE)
    fresh = _code_from_last_message()
    verification._records[PHONE].expires_at = verification.time.time() - 1
    expired = await verification.verify_code(PHONE, fresh)
    check("expired code rejected", expired["reason"] == "expired", expired)

    # --- attempt cap ---
    verification.reset()
    await verification.send_code(PHONE)
    real = _code_from_last_message()
    bad = "000000" if real != "000000" else "111111"
    for _ in range(verification.MAX_VERIFY_ATTEMPTS):
        await verification.verify_code(PHONE, bad)
    locked = await verification.verify_code(PHONE, real)
    check(
        "correct code rejected after attempt cap",
        locked["reason"] == "too_many_attempts",
        locked,
    )

    print(f"\nAll checks passed ({len(sent)} stubbed messages).")


if __name__ == "__main__":
    asyncio.run(main())
