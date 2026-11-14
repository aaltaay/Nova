"""Pydantic bodies for localhost bot routes."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HeartbeatBody(BaseModel):
    brain_session_id: str | None = None


class CapsPatch(BaseModel):
    """``PATCH /api/bot/session``: one venue's sleeve, your risk per trade (``bot.caps``). Any other key is kept so
    the refusal can name it (ADR 072: the levels, keys and stocks went with the bots)."""
    model_config = ConfigDict(extra="allow")

    caps: dict | None = None
    brain_session_id: str | None = None


class ClaimBody(BaseModel):
    """``POST /api/bot/session/claim``: the brain that claims the exclusive L2 session."""
    brain_session_id: str | None = None


class ActionBody(BaseModel):
    kind: str | None = None
    action: str | None = None
    symbol: str
    brain_session_id: str | None = None
    idempotency_key: str | None = None
    percent: int | None = None
    qty: float | None = None
    shares: float | None = None
    offset_dollars: float | None = None
