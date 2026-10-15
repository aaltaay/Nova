"""Pydantic bodies for localhost bot routes."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionPatch(BaseModel):
    # The master ceiling (ADR 042): the most any setup may do on this venue.
    level: int | None = Field(default=None, ge=0, le=3)
    armed: bool | None = None
    # Retired (ADR 042): kept in the model so a PATCH that sends it is refused out loud
    # (400 BOT_SETUP_RETIRED), never ignored.
    setup: str | None = None
    # ADR 031 / 042: Off (0), Eyes (1) or Strategy (2) for every setup with a scanner.
    setup_levels: dict[str, Any] | None = None
    # Retired (ADR 056): kept so a PATCH that sends it is refused out loud (400 BOT_BREAKERS_RETIRED).
    breakers: dict[str, Any] | None = None
    # This venue's Bot stocks, through stock mode's rules (the answer adds ``refused``).
    symbol_allowlist: list[str] | None = None
    # One venue's sleeve (ADR 042 E): {venue?, risk_usd?, max_shares?, ...}.
    caps: dict[str, Any] | None = None
    brain_session_id: str | None = None
    desk_arm_token: str | None = None


class ArmBody(BaseModel):
    brain_session_id: str | None = None


class SwitchBody(BaseModel):
    """The Bot switch (ADR 044): ``on`` is the master at Strategy and Activate; off, the master at Eyes."""
    on: bool
    brain_session_id: str | None = None


class KeyBody(BaseModel):
    """A family key (bot.md, "The three keys"): ``strategy`` or ``live_trader``, on or off, on the desk venue."""
    family: str
    on: bool
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

