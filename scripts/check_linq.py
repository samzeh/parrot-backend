r"""Diagnostic: confirm the Linq token works and list the lines it can send from.

Run from the repo root:  venv\Scripts\python.exe scripts\check_linq.py
"""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv(override=True)

BASE = os.getenv("LINQ_API_BASE", "https://api.linqapp.com/api/partner/v3")
KEY = os.getenv("LINQ_API_KEY") or os.getenv("LINQ_API_V3_API_KEY")


def main() -> int:
    if not KEY:
        print("LINQ_API_KEY missing")
        return 1

    headers = {"Authorization": f"Bearer {KEY}"}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        response = client.get(f"{BASE}/phone_numbers")
        print("GET /phone_numbers ->", response.status_code)
        print(response.text[:2000])
    return 0 if response.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
