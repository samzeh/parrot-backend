"""Thin Gemini API wrapper used by Polly."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

load_dotenv(override=True)

# Flash-Lite has a separate (usually higher) free-tier daily quota than 3.6-flash.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.5-flash-lite,gemini-3.5-flash,gemini-flash-lite-latest",
    ).split(",")
    if m.strip()
]
MAX_TOOL_ROUNDS = 5

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    pass


def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError(
            "GEMINI_API_KEY is not set. Add it to your .env file to enable Polly."
        )
    return genai.Client(api_key=api_key)


def history_to_contents(history: list[dict[str, str]]) -> list[types.Content]:
    contents: list[types.Content] = []
    for message in history:
        role = message.get("role", "user")
        gemini_role = "model" if role in {"assistant", "model"} else "user"
        contents.append(
            types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(text=message.get("content", ""))],
            )
        )
    return contents


def _is_quota_error(exc: ClientError) -> bool:
    message = str(exc)
    return "RESOURCE_EXHAUSTED" in message or "429" in message


def _friendly_api_error(exc: ClientError, model: str) -> str:
    message = str(exc)
    if _is_quota_error(exc):
        if "PerDay" in message or "per day" in message.lower():
            return (
                f"Daily free-tier quota exhausted for {model} "
                "(Gemini caps some models at ~20 requests/day). "
                "Waiting minutes won't help — switch GEMINI_MODEL in .env "
                "(e.g. gemini-3.1-flash-lite) or enable billing in AI Studio."
            )
        retry = re.search(r"retry in ([0-9.]+)s", message, re.I)
        wait = f" Wait ~{int(float(retry.group(1))) + 1}s." if retry else " Wait a bit."
        return (
            f"Gemini per-minute rate limit hit for {model}.{wait} "
            "Tool calls use 2+ requests each."
        )
    if "NOT_FOUND" in message or "no longer available" in message:
        return (
            f"Model '{model}' isn't available for this API key. "
            "Set GEMINI_MODEL in .env (try gemini-3.1-flash-lite) and restart."
        )
    if "PERMISSION_DENIED" in message or "403" in message:
        return (
            "Gemini permission denied for this API key/model. "
            "Check the key in Google AI Studio."
        )
    return f"Gemini API error: {exc}"


def _extract_text(response: Any) -> str:
    try:
        text = (response.text or "").strip()
        if text:
            return text
    except Exception:
        pass

    chunks: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                chunks.append(part_text)
    return "\n".join(chunks).strip()


def _candidate_models(preferred: str | None) -> list[str]:
    primary = preferred or DEFAULT_MODEL
    models = [primary]
    for model in FALLBACK_MODELS:
        if model not in models:
            models.append(model)
    return models


def generate_with_tools(
    *,
    system_instruction: str,
    history: list[dict[str, str]],
    user_message: str,
    tools: list[Any],
    model: str | None = None,
) -> str:
    """Generate a reply with a manual tool-calling loop (more reliable than AFC)."""
    client = get_client()
    tool_map = {fn.__name__: fn for fn in tools}
    last_error: GeminiError | None = None

    for model_name in _candidate_models(model):
        try:
            return _generate_with_model(
                client=client,
                model_name=model_name,
                system_instruction=system_instruction,
                history=history,
                user_message=user_message,
                tools=tools,
                tool_map=tool_map,
            )
        except ClientError as exc:
            friendly = GeminiError(_friendly_api_error(exc, model_name))
            if _is_quota_error(exc):
                logger.warning("Quota hit on %s — trying fallback model", model_name)
                last_error = friendly
                continue
            raise friendly from exc

    assert last_error is not None
    raise last_error


def _generate_with_model(
    *,
    client: genai.Client,
    model_name: str,
    system_instruction: str,
    history: list[dict[str, str]],
    user_message: str,
    tools: list[Any],
    tool_map: dict[str, Any],
) -> str:
    contents = history_to_contents(history)
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        )
    )

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.7,
        max_output_tokens=512,
    )

    logger.info("Using Gemini model %s", model_name)

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        function_calls = list(getattr(response, "function_calls", None) or [])
        if not function_calls:
            text = _extract_text(response)
            if not text:
                raise GeminiError("Gemini returned an empty response.")
            return text

        model_content = response.candidates[0].content
        contents.append(model_content)

        result_parts: list[types.Part] = []
        for call in function_calls:
            fn = tool_map.get(call.name)
            if fn is None:
                payload: dict[str, Any] = {"error": f"Unknown tool: {call.name}"}
            else:
                args = dict(call.args or {})
                try:
                    payload = fn(**args)
                except Exception as exc:  # noqa: BLE001 - surface tool errors to model
                    payload = {"error": str(exc)}
            result_parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response={"result": payload},
                )
            )

        contents.append(types.Content(role="user", parts=result_parts))

    raise GeminiError("Too many tool rounds — try a simpler request.")
