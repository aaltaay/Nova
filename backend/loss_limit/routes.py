"""The daily loss limit on the wire: ``GET`` and ``PUT /api/loss-limit`` (ADR 056).

Shape: ``architecture/schema/loss-limit.md``. ``PUT`` saves the setting off the loop, then clears
today's warnings and trips on every account and restarts every 10-second wait, so a raised limit or
an unchecked No new buys lifts the lock at once and the watcher reads the loss afresh.
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
    LOSS_LIMIT_MAX_USD,
    LOSS_LIMIT_MIN_USD,
    LOSS_LIMIT_REASON_INVALID,
    LOSS_LIMIT_WARN_FRACTION,
)
from loss_limit import gate, settings, state, watch

logger = logging.getLogger(__name__)
router = APIRouter(tags=["loss-limit"])


def view(now: float | None = None) -> dict[str, Any]:
    ts = time.time() if now is None else float(now)
    day, records, error = state.records(ts)
    counts = watch.last_counts()
    accounts: dict[str, Any] = {}
    for account in LOSS_LIMIT_ACCOUNTS:
        row = records.get(account, {})
        last = counts.get(account, {})
        accounts[account] = {
            "name": gate.account_name(account),
            "counted_at": last.get("at"), "pnl": last.get("pnl"), "loss": last.get("loss"),
            "unknown": last.get("unknown"), "stocks": last.get("stocks", []),
            "held_before": last.get("held_before", []), "costs_unknown": last.get("costs_unknown", 0),
            "warned_at": row.get("warned_at"), "warned_loss": row.get("warned_loss"),
            "tripped_at": row.get("tripped_at"), "tripped_loss": row.get("tripped_loss"),
            "limit_usd": row.get("limit_usd"), "sell": row.get("sell"), "sold": row.get("sold"),
            "sell_error": row.get("sell_error"),
            "no_new_buys": gate.stopped(account, ts),
        }
    return {"schema_version": 1, "settings": settings.current(), "day": day, "until": state.until(ts),
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
    logger.info("LOSS LIMIT: changed from %s to %s; today's warnings and trips cleared", before, after)
    return await asyncio.to_thread(view)
