"""``GET /api/ibkr/depth/lines`` and ``PATCH /api/ibkr/depth/lending`` (ADR 043 decision 6).

Included in ``routes.trading``'s ``/api/ibkr`` router, beside the other depth routes.
The switch needs the desk's API key even on loopback, like a bot write: it decides
whether Nova may take a Trader tab's Level 2 line. Both answer the lines view, so
the Bots page redraws from the answer. A session file that cannot be written is a
503 with the reason, and the switch is unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool

from auth import require_bot_auth
from line_lending import loans, setting, view
from line_lending.constants_line_lending import (
    LENDING_OFF_WHY,
    LINE_LENDING_SWITCH_AUDIT_ACTION,
    LOAN_END_OFF,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class LendingSwitch(BaseModel):
    on: StrictBool


@router.get("/depth/lines")
def depth_lines() -> dict[str, Any]:
    return view.build()


@router.patch("/depth/lending", dependencies=[Depends(require_bot_auth)])
async def depth_lending(body: LendingSwitch) -> dict[str, Any]:
    try:
        before = setting.set_on(body.on)
    except Exception as exc:
        logger.exception("line lending: the switch could not be saved")
        raise HTTPException(status_code=503, detail={
            "reason": "LINE_LENDING_UNSAVED", "field": "on",
            "error": f"the bot session could not be written ({type(exc).__name__}): line lending is unchanged",
        }) from exc
    ended = 0 if body.on else await loans.end_all(LOAN_END_OFF, LENDING_OFF_WHY)
    if before != body.on:
        _audit(body.on, ended)
    return view.build()


def _audit(on: bool, ended: int) -> None:
    from bot.audit import record

    word = "on" if on else "off"
    tail = f" ({ended} loan{'s' if ended != 1 else ''} ended)" if ended else ""
    try:
        record(action=LINE_LENDING_SWITCH_AUDIT_ACTION, outcome=word, reason=f"line lending switched {word}{tail}",
               inputs={"on": on, "ended": ended})
    except Exception:
        logger.exception("line lending: the switch's audit line could not be written")
