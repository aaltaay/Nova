"""``/api/traders`` (ADR 072, ``traders.md`` "On the wire"): the AI traders' switches. Loopback only; writes need
the desk's API key (``auth.require_agent_key``); the phone is refused by the request guard (``REMOTE_VIEW_ONLY``).

- ``GET /api/traders`` -- ``{schema_version, generated_at, venue, traders: {claude, brain}, error}``.
- ``PUT /api/traders/{trader}/switch {on}`` -- the ``GET`` shape, or ``409 {reason, error}`` when On is refused;
  ``404 TRADER_UNKNOWN`` for another name. Only the operator flips a switch: a request carrying ``X-Agent-Seat``
  (Claude's own session) is refused ``TRADER_OPERATOR_ONLY``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from agent_desk.routes import require_local
from auth import require_agent_key
from constants_owners import AI_TRADERS, OWNER_NAMES
from constants_traders import TRADER_OPERATOR_ONLY, TRADER_UNKNOWN
from traders import off, switches, view

router = APIRouter(prefix="/api/traders", tags=["traders"], dependencies=[Depends(require_local)])


class SwitchBody(BaseModel):
    on: bool


def _refuse(status: int, code: str, text: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"reason": code, "error": text})


@router.get("")
def get_traders() -> dict[str, Any]:
    return view.snapshot()


@router.put("/{trader}/switch", dependencies=[Depends(require_agent_key)])
async def put_switch(trader: str, body: SwitchBody,
                     x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    if trader not in AI_TRADERS:
        raise _refuse(404, TRADER_UNKNOWN, f"Nova has no trader called {trader!r}: Claude or the brain")
    name = OWNER_NAMES[trader]
    if x_agent_seat is not None:
        raise _refuse(409, TRADER_OPERATOR_ONLY, f"Only you switch {name} On or Off, from the desk.")
    if body.on:
        if why := switches.on_refusal(trader):
            raise _refuse(409, why[0], why[1])
        switches.set_switch(trader, True, "you")
    elif switches.is_on(trader):
        await off.turn_off(trader, "you")
    return view.snapshot()
