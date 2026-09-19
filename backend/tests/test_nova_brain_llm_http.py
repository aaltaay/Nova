"""OpenRouter HTTP helper -- stubbed requests only."""
from __future__ import annotations

from constants_bot import BOT_LLM_DEFAULT_MODEL, BOT_LLM_HTTP_TITLE, BOT_LLM_OPENROUTER_BASE_URL
from nova_brain import llm_http


class _Resp:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "{\"proposals\":[]}"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }


def test_chat_uses_openrouter_defaults_and_headers(monkeypatch):
    monkeypatch.delenv("NOVA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("NOVA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("NOVA_LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    seen: dict = {}

    def fake_post(url, json, headers, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        seen["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(llm_http.requests, "post", fake_post)
    out = llm_http.chat("sys", "user")
    assert seen["url"] == f"{BOT_LLM_OPENROUTER_BASE_URL}/chat/completions"
    assert seen["json"]["model"] == BOT_LLM_DEFAULT_MODEL
    assert seen["json"]["response_format"] == {"type": "json_object"}
    assert seen["headers"]["Authorization"] == "Bearer or-key"
    assert seen["headers"]["X-Title"] == BOT_LLM_HTTP_TITLE
    assert out["content"].startswith("{")
