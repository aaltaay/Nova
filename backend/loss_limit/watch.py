"""The daily loss limit's watcher: count every account each second, act once a line holds 10 s (ADR 056, ADR 061).

Each line that is set -- the Account line always, the You and Bots lines when they have dollars --
has two marks per account: 80% of its limit (Warn me) and the limit itself. A mark is crossed only
when that line's loss stays at or past it for ``LOSS_LIMIT_CONFIRM_SEC`` in a row; one reading back
under it, or an unknown one, starts the wait again. Each mark acts once per account, line and day:

- 80%: with Warn me, a warning (``warned_at``) the desk turns into a notice and a voice line.
- the limit: the trip (``tripped_at``) -- No new buys reads it (``loss_limit.gate``: the Account
  line holds everyone, a side line only its side) and the desk says it -- and with Auto sell, what
  that line counts open from today is closed (``loss_limit.sell``) and what was sold is written
  beside it (``sold``, ``sell_error``). The trip is saved with ``sell: "pending"`` before any order
  goes out and ``"done"`` once the closes answered, so a sale a restart interrupted is taken up again
  by the next pass (it closes only what is still held from today) and the desk waits for the answer
  before it says what was sold.

One sale per account per pass: once a line has sold, this pass's count is out of date, so a second
line that trips in the same pass is saved as ``pending`` and sells on the next pass, from a fresh
count -- never twice for the same shares.

The last count per account is kept in memory for ``GET /api/loss-limit``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from constants_loss_limit import (
    LOSS_LIMIT_ACCOUNTS,
    LOSS_LIMIT_CONFIRM_SEC,
    LOSS_LIMIT_POLL_SEC,
    LOSS_LIMIT_SIDES,
    LOSS_LIMIT_WARN_FRACTION,
)
from loss_limit import accounts, settings, state
from loss_limit.count import Count

logger = logging.getLogger(__name__)

_last: dict[str, dict[str, Any]] = {}            # account -> {at, pnl, loss, unknown, stocks, held_before, sides, ...}
_since: dict[tuple[str, str, str], float] = {}   # (account, line, "warn" | "trip") -> first second past that mark
_selling: set[str] = set()                       # accounts with an Auto sell running in this process


def last_counts() -> dict[str, dict[str, Any]]:
    return {k: dict(v) for k, v in _last.items()}


def _held_for(key: tuple[str, str, str], past: bool, now: float) -> bool:
    """True once ``key``'s mark has held for the confirm window; resets when it is not past."""
    if not past:
        _since.pop(key, None)
        return False
    first = _since.setdefault(key, now)
    return now - first >= LOSS_LIMIT_CONFIRM_SEC


def reset_waits() -> None:
    """Every line's 10-second wait starts again (the setting changed)."""
    _since.clear()


async def _sell(account: str, line: str, count: Count, now: float) -> None:
    """Auto sell what ``count`` holds open from today for ``line``, then mark the sale done.

    Each close is added to ``sold`` the moment it answers (PR #1004 review): a restart after one close
    of several keeps it, and the resumed sale adds only what is still held."""
    from loss_limit.sell import sell_opened_today

    if account in _selling:
        return
    _selling.add(account)

    def saved(close: dict[str, Any]) -> None:
        previous = state.record(account, now, line=line).get("sold") or []
        state.write(account, {"sold": list(previous) + [close]}, now, line=line)

    try:
        try:
            sold = await sell_opened_today(account, count.opened_today(line), on_close=saved, line=line)
            error = next((s["error"] for s in sold if not s["ok"]), None)
        except Exception as exc:
            logger.exception("LOSS LIMIT: Auto sell of the %s line on %s failed", line, account)
            error = f"{type(exc).__name__}: {exc}"
        state.write(account, {"sell_error": error, "sell": "done"}, now, line=line)
    finally:
        _selling.discard(account)


async def check(account: str, count: Count, now: float) -> None:
    """Compare ``account``'s count with today's lines and act on any mark that held."""
    current = settings.current()
    _last[account] = {"at": now, "pnl": count.pnl, "loss": count.loss, "unknown": count.unknown,
                      "stocks": count.stocks, "held_before": count.held_before,
                      "costs_unknown": count.costs_unknown,
                      "sides": {side: count.pnl_of(side) for side in LOSS_LIMIT_SIDES}}
    sold = False                  # a line sold this pass: the count is out of date for another sale
    for line in settings.lines_on(current):
        limit = int(settings.line_limit(current, line) or 0)
        loss = count.loss_of(line)
        row = state.record(account, now, line=line)
        warn_past = loss is not None and loss >= LOSS_LIMIT_WARN_FRACTION * limit
        trip_past = loss is not None and loss >= limit
        if _held_for((account, line, "warn"), warn_past, now) and current["warn"] and not row.get("warned_at"):
            state.write(account, {"warned_at": now, "warned_loss": round(loss, 2), "limit_usd": limit}, now, line=line)
        auto_sell = bool(current["auto_sell"])
        if _held_for((account, line, "trip"), trip_past, now) and not row.get("tripped_at"):
            fields: dict[str, Any] = {"tripped_at": now, "tripped_loss": round(loss, 2), "limit_usd": limit}
            if auto_sell:
                fields["sell"] = "pending"           # saved before any order goes out: a restart resumes it
            state.write(account, fields, now, line=line)
            logger.warning("LOSS LIMIT: the %s line on %s is down %.2f against its %s limit -- tripped%s", line,
                           account, loss, limit, ", Auto sell closes what it opened today" if auto_sell else "")
            if auto_sell and not sold:
                await _sell(account, line, count, now)
                sold = True
        elif row.get("sell") == "pending" and count.pnl is not None and account not in _selling and not sold:
            # A sale a restart (or a failed save) left unfinished: close what is still held from today.
            logger.warning("LOSS LIMIT: resuming the Auto sell of the %s line on %s that did not finish", line, account)
            await _sell(account, line, count, now)
            sold = True


async def pass_once(now: float | None = None) -> None:
    ts = time.time() if now is None else float(now)
    for account in LOSS_LIMIT_ACCOUNTS:
        # Live waits on the IB loop (``call_on_ib``), so it is read off this loop; the practice ledgers
        # live on this loop and are read in place, never from another thread.
        if account == "live":
            count = await asyncio.to_thread(accounts.read, account, ts)
        else:
            count = accounts.read(account, ts)
        await check(account, count, ts)


async def watch_loop() -> None:
    while True:
        try:
            await pass_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("LOSS LIMIT: the watcher's pass failed")
        await asyncio.sleep(LOSS_LIMIT_POLL_SEC)


def reset_for_tests() -> None:
    _last.clear()
    _since.clear()
    _selling.clear()
