r"""Hit the running verification endpoints over HTTP.

Safe by default: only error/no-op paths are exercised, so no real iMessage is
sent unless you pass a recipient number.

    venv\Scripts\python.exe scripts\test_verification_http.py
    venv\Scripts\python.exe scripts\test_verification_http.py +15551234567
"""

from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"


def show(label: str, response: httpx.Response) -> None:
    retry = response.headers.get("Retry-After")
    suffix = f" Retry-After={retry}" if retry else ""
    print(f"{label}: {response.status_code}{suffix} {response.text[:220]}")


def main() -> int:
    recipient = sys.argv[1] if len(sys.argv) > 1 else None

    with httpx.Client(timeout=40.0) as client:
        show("GET  /verification/status ", client.get(f"{BASE}/verification/status"))
        show(
            "POST /verification/verify  (no code issued)",
            client.post(
                f"{BASE}/verification/verify",
                json={"phone": "+15555550188", "code": "000000"},
            ),
        )
        show(
            "POST /verification/send    (malformed number)",
            client.post(f"{BASE}/verification/send", json={"phone": "12"}),
        )

        if not recipient:
            print("\nPass a phone number as an argument to test real delivery.")
            return 0

        show(
            "POST /verification/send    (real delivery)",
            client.post(f"{BASE}/verification/send", json={"phone": recipient}),
        )
        show(
            "POST /verification/resend  (expect 429 cooldown)",
            client.post(f"{BASE}/verification/resend", json={"phone": recipient}),
        )
        show(
            "POST /verification/verify  (wrong code)",
            client.post(
                f"{BASE}/verification/verify",
                json={"phone": recipient, "code": "000000"},
            ),
        )
        print("\nCheck the phone for the code, then verify it with:")
        print(
            f'  curl.exe -X POST {BASE}/verification/verify -H "Content-Type: application/json" '
            f'-d "{{\\"phone\\":\\"{recipient}\\",\\"code\\":\\"123456\\"}}"'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
