"""Phone verification FastAPI routes — send, resend, and check OTP codes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import verification
from services.linq import can_send_outbound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verification", tags=["verification"])


class SendCodeRequest(BaseModel):
    phone: str = Field(..., description="Recipient phone number, E.164 preferred")


class SendCodeResponse(BaseModel):
    phone: str
    delivered: bool
    expires_in: int
    resend_available_in: int


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str = Field(..., min_length=1, max_length=12)


class VerifyCodeResponse(BaseModel):
    phone: str
    verified: bool
    reason: str | None = None
    attempts_remaining: int | None = None


async def _issue(phone: str) -> SendCodeResponse:
    try:
        result = await verification.send_code(phone)
    except verification.InvalidPhoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except verification.RateLimitedError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except verification.DeliveryError as exc:
        logger.error("Verification delivery failed for %s: %s", phone, exc)
        raise HTTPException(
            status_code=502, detail="Could not deliver the verification code."
        ) from exc

    return SendCodeResponse(**result)  # type: ignore[arg-type]


@router.get("/status")
async def status() -> dict[str, Any]:
    """Quick check that the Linq line is ready to send codes."""
    return {
        "can_send": can_send_outbound(),
        "code_length": verification.CODE_LENGTH,
        "expires_in": verification.CODE_TTL_SECONDS,
        "resend_cooldown": verification.RESEND_COOLDOWN_SECONDS,
    }


@router.post("/send", response_model=SendCodeResponse)
async def send(body: SendCodeRequest) -> SendCodeResponse:
    """Generate a code and deliver it over iMessage."""
    return await _issue(body.phone)


@router.post("/resend", response_model=SendCodeResponse)
async def resend(body: SendCodeRequest) -> SendCodeResponse:
    """Issue a fresh code through the same send path, subject to rate limits."""
    return await _issue(body.phone)


@router.post("/verify", response_model=VerifyCodeResponse)
async def verify(body: VerifyCodeRequest) -> VerifyCodeResponse:
    try:
        result = await verification.verify_code(body.phone, body.code)
    except verification.InvalidPhoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return VerifyCodeResponse(**result)  # type: ignore[arg-type]
