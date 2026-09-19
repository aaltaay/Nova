"""OpenRouter chat/completions client. Key stays in env. No live calls in CI."""
from __future__ import annotations

from typing import Any

import requests

from bot.llm_guard import llm_api_key, llm_base_url, llm_model_id
from constants_bot import (
    BOT_LLM_HTTP_REFERER,
    BOT_LLM_HTTP_TIMEOUT_SEC,
    BOT_LLM_HTTP_TITLE,
)


def chat(system: str, user: str) -> dict[str, Any]:
    base = llm_base_url().rstrip("/")
    key = llm_api_key()
    model = llm_model_id()
    if not (base and key and model):
        raise RuntimeError("LLM is not configured")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if "openrouter.ai" in base:
        headers["HTTP-Referer"] = BOT_LLM_HTTP_REFERER
        headers["X-Title"] = BOT_LLM_HTTP_TITLE
        body["usage"] = {"include": True}
        body["response_format"] = {"type": "json_object"}
    res = requests.post(
        f"{base}/chat/completions",
        json=body,
        headers=headers,
        timeout=BOT_LLM_HTTP_TIMEOUT_SEC,
    )
    res.raise_for_status()
    data = res.json()
    choices = data.get("choices") or []
    message = (choices[0] or {}).get("message") if choices else {}
    content = (message or {}).get("content") or ""
    return {"content": str(content), "usage": data.get("usage") or {}}
