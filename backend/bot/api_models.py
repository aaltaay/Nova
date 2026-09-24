"""Pydantic bodies for localhost bot routes."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionPatch(BaseModel):
    level: int | None = Field(default=None, ge=0, le=3)
    armed: bool | None = None
    strategy: str | None = None
    setup: str | None = None
    # ADR 031: Off (0) or Eyes (1) for a setup with a scanner other than the chosen one.
    setup_levels: dict[str, Any] | None = None
    # The loss breakers, per venue (operator ask 2026-09-24): {venue?, soft_usd?, hard_usd?}.
    breakers: dict[str, Any] | None = None
    symbol_allowlist: list[str] | None = None
    caps: dict[str, Any] | None = None
    advise: dict[str, Any] | None = None
    reenable: bool | None = None
    brain_session_id: str | None = None
    desk_arm_token: str | None = None


class ArmBody(BaseModel):
    reenable: bool = False
    brain_session_id: str | None = None


class HeartbeatBody(BaseModel):
    brain_session_id: str | None = None


class AllowlistBody(BaseModel):
    symbol: str
    op: Literal["add", "remove"] = "add"


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


class ProposalBody(BaseModel):
    symbol: str
    side: str
    kind: str | None = None
    action: str | None = None
    shortcut: str | None = None
    reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    brain_session_id: str | None = None
    qty: float | None = None
    shares: float | None = None


class FocusBody(BaseModel):
    symbol: str | None = None
    symbols: list[str] | None = None


class LiveSyncBody(BaseModel):
    live: list[str]


class AdviseBody(BaseModel):
    symbol: str
    depth: int | None = None
    force_refresh: bool = False

