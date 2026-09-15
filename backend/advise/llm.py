"""OpenRouter chat for the Advise worker. Never used for orders."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from constants_advise import (
    ADVISE_HTTP_REFERER,
    ADVISE_HTTP_TITLE,
    ADVISE_LLM_MAX_TOKENS,
    ADVISE_LLM_TEMPERATURE,
    ADVISE_LLM_TIMEOUT_SEC,
    ADVISE_OPENROUTER_URL,
    advise_model_id,
)


class AdviseLlmError(RuntimeError):
    pass


def openrouter_key() -> str:
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def chat(system: str, user: str, *, model: str | None = None) -> str:
    key = openrouter_key()
    if not key:
        raise AdviseLlmError("OPENROUTER_API_KEY is not set")
    payload = {
        "model": model or advise_model_id(),
        "temperature": ADVISE_LLM_TEMPERATURE,
        "max_tokens": ADVISE_LLM_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    request = urllib.request.Request(
        ADVISE_OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": ADVISE_HTTP_REFERER,
            "X-Title": ADVISE_HTTP_TITLE,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=ADVISE_LLM_TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise AdviseLlmError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AdviseLlmError(f"OpenRouter unreachable: {exc.reason}") from exc
    return _content_from_response(body)


def _content_from_response(body: dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise AdviseLlmError("OpenRouter returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        ]
        joined = "\n".join(p for p in parts if p).strip()
        if joined:
            return joined
    raise AdviseLlmError("OpenRouter message content was empty")
