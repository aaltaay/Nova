"""The daily loss limit on the wire: ``GET`` and ``PUT /api/loss-limit`` (ADR 056, ADR 061).

Shape: ``architecture/schema/loss-limit.md``. ``PUT`` saves the setting off the loop, then clears
today's warnings and trips on every account and line and restarts every 10-second wait, so a raised
limit, a line turned off or an unchecked No new buys lifts the lock at once and the watcher reads the
loss afresh.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from constants_loss_limit import (
    LOSS_LIMIT_ACCOUNTS,
    LOSS_LIMIT_CONFIRM_SEC,
    LOSS_LIMIT_LINE_ACCOUNT,
    LOSS_LIMIT_LINES,
    LOSS_LIMIT_MAX_USD,
    LOSS_LIMIT_MIN_USD,
    LOSS_LIMIT_REASON_INVALID,
    LOSS_LIMIT_SIDES,
    LOSS_LIMIT_WARN_FRACTION,
)
from loss_limit import gate, settings, state, watch

logger = logging.getLogger(__name__)
router = APIRouter(tags=["loss-limit"])


_RECORD = ("warned_at", "warned_loss", "tripped_at", "tripped_loss", "limit_usd", "sell", "sold", "sell_error")


def _line(account: str, line: str, current: dict[str, Any], row: dict[str, Any], last: dict[str, Any],
          ts: float) -> dict[str, Any]:
    if line == LOSS_LIMIT_LINE_ACCOUNT:
        pnl, loss = last.get("pnl"), last.get("loss")
    else:
        pnl = (last.get("sides") or {}).get(line)
        loss = None if pnl is None else max(0.0, -float(pnl))
    return {"on": settings.line_limit(current, line) is not None, "pnl": pnl, "loss": loss,
            **{key: row.get(key) for key in _RECORD}, "no_new_buys": gate.line_stop(account, line, ts)}


def view(now: float | None = None) -> dict[str, Any]:
    ts = time.time() if now is None else float(now)
    day, records, error = state.records(ts)
    counts = watch.last_counts()
    current = settings.current()
    accounts: dict[str, Any] = {}
    for account in LOSS_LIMIT_ACCOUNTS:
        rows = records.get(account, {})
        last = counts.get(account, {})
        accounts[account] = {
            "name": gate.account_name(account),
            "counted_at": last.get("at"), "pnl": last.get("pnl"), "loss": last.get("loss"),
            "unknown": last.get("unknown"), "stocks": last.get("stocks", []),
            "held_before": last.get("held_before", []), "costs_unknown": last.get("costs_unknown", 0),
            "lines": {line: _line(account, line, current, rows.get(line, {}), last, ts) for line in LOSS_LIMIT_LINES},
            "no_new_buys": {side: gate.stopped(account, ts, actor=side) for side in LOSS_LIMIT_SIDES},
        }
    return {"schema_version": 2, "settings": current, "day": day, "until": state.until(ts),
            "accounts": accounts, "error": error,
            "rules": {"min_usd": LOSS_LIMIT_MIN_USD, "max_usd": LOSS_LIMIT_MAX_USD,
                      "warn_fraction": LOSS_LIMIT_WARN_FRACTION, "confirm_sec": LOSS_LIMIT_CONFIRM_SEC}}


@router.get("/api/loss-limit")
async def get_loss_limit() -> dict[str, Any]:
    return await asyncio.to_thread(view)


@router.put("/api/loss-limit")
async def put_loss_limit(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Send the change as JSON") from exc
    try:
        before, after = await asyncio.to_thread(settings.update, body)
    except settings.Invalid as exc:
        raise HTTPException(status_code=400, detail=str(exc),
                            headers={"X-Nova-Reason": LOSS_LIMIT_REASON_INVALID}) from exc
    except OSError as exc:
        logger.exception("LOSS LIMIT: could not save the setting")
        raise HTTPException(status_code=503, detail=(f"Nova could not save the loss limit ({type(exc).__name__}: "
                                                     f"{exc}); the setting is unchanged")) from exc
    await asyncio.to_thread(state.clear)
    watch.reset_waits()
    logger.info("LOSS LIMIT: changed from %s to %s; today's warnings and trips on every line cleared", before, after)
    return await asyncio.to_thread(view)
