"""HTTP client for the localhost bot API. Never places except via /action."""
from __future__ import annotations

import os
from typing import Any

import requests

from constants import NOVA_API_KEY_HEADER
from constants_bot import BOT_BRAIN_SESSION_ID

DEFAULT_BASE = "http://127.0.0.1:8000"


class BotApiClient:
    def __init__(
        self,
        *,
        base: str | None = None,
        api_key: str | None = None,
        brain_id: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base = (base or os.environ.get("NOVA_API_BASE") or DEFAULT_BASE).rstrip("/")
        self.api_key = (api_key if api_key is not None else os.environ.get("NOVA_API_KEY") or "").strip()
        self.brain_id = (brain_id or os.environ.get("NOVA_BRAIN_SESSION_ID") or BOT_BRAIN_SESSION_ID).strip()
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {NOVA_API_KEY_HEADER: self.api_key, "X-Nova-Brain-Session": self.brain_id}
        if extra:
            headers.update(extra)
        return headers

    def get(self, path: str) -> dict[str, Any]:
        res = self.session.get(self.base + path, headers=self._headers(), timeout=self.timeout)
        res.raise_for_status()
        return res.json()

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        res = self.session.post(
            self.base + path,
            json=body or {},
            headers=self._headers(),
            timeout=self.timeout,
        )
        res.raise_for_status()
        return res.json()

    def session_get(self) -> dict[str, Any]:
        return self.get("/api/bot/session")

    def claim(self) -> dict[str, Any]:
        return self.post("/api/bot/session/claim", {"brain_session_id": self.brain_id})

    def heartbeat(self) -> dict[str, Any]:
        return self.post("/api/bot/session/heartbeat", {"brain_session_id": self.brain_id})

    def watch(self) -> dict[str, Any]:
        return self.get("/api/bot/watch")

    def fire(self, kind: str, symbol: str) -> dict[str, Any]:
        return self.post(
            "/api/bot/action",
            {"kind": kind, "symbol": symbol, "brain_session_id": self.brain_id},
        )

    def propose(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = dict(body)
        payload.pop("qty", None)
        payload.pop("shares", None)
        payload["brain_session_id"] = self.brain_id
        return self.post("/api/bot/proposals", payload)

    def charge_llm(self, usd: float) -> dict[str, Any]:
        return self.post("/api/bot/llm/spend", {"usd": usd})
