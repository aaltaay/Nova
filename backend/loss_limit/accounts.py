"""Each account's fills today and what it holds, for the daily loss limit's count (ADR 056).

- **Paper**, and **Sim at the live edge**: the practice ledger -- every order filled since its
  04:00 ET day began, with its commission and fees, and its positions at the ledger's own mark.
  Sim off the live edge is a replay: nothing is counted (a replay's P&L is not today's).
- **Live**: IBKR's own -- today's executions (``ib.fills()``, read back at every connect) for the
  account Nova is logged into, and ``ib.portfolio()``'s positions at IBKR's mark. Stocks only:
  the execution door trades nothing else. An execution whose commission report has not arrived
  is a cost IBKR has not said yet (``Fill.cost`` None). IBKR not READY is an unknown.

**Whose fill (ADR 061)** -- ``Fill.by``, from the order's own stamps, never from its side, size or
time: a practice order is the bots' when its source is ``bot`` or it carries a ``bot_id`` (the rule
the Account page's by-source split uses, ``practice.history``), or when it is a bot's own close --
those go out as source ``flatten`` with the bot's origin (``bot``, ``bot_api``, ``live_trader``). A
side line's Auto sell is that side's (``loss_limit_you`` / ``loss_limit_bots``). Nova's own closes --
KILL, the day cover, a margin call, the Account line's Auto sell, a flatten with no origin -- are
None: whose shares they close decides (``loss_limit.count``). Everything else is yours. Every Live
fill is yours: a bot never trades Live (Invariant #7).

Every read answers ``(count, unknown)``; ``unknown`` says why there is nothing to compare.
Blocking: the watcher calls ``read`` off the event loop.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from constants_loss_limit import (
    LOSS_LIMIT_BOT_CLOSE_ORIGINS,
    LOSS_LIMIT_LINE_BOTS,
    LOSS_LIMIT_LINE_YOU,
    LOSS_LIMIT_SIDE_ORIGINS,
)
from loss_limit.count import Count, Fill, Held, count

logger = logging.getLogger(__name__)

_IB_READ_TIMEOUT_SEC = 3.0
_UNSET = 1e300      # IBKR's unset double is 1.797e308


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and abs(out) < _UNSET else None


_SIDE_OF_ORIGIN = {origin: side for side, origin in LOSS_LIMIT_SIDE_ORIGINS.items()}
_NOVA_SOURCES = frozenset({"flatten", "kill", "cancel_working"})


def by_of(row: dict[str, Any]) -> str | None:
    """Whose order a practice ledger row is: ``you`` | ``bots`` | None (one of Nova's own closes)."""
    source = str(row.get("order_source") or "")
    origin = row.get("order_origin")
    if source == "bot" or row.get("bot_id") is not None or origin in LOSS_LIMIT_BOT_CLOSE_ORIGINS:
        return LOSS_LIMIT_LINE_BOTS
    if origin in _SIDE_OF_ORIGIN:
        return _SIDE_OF_ORIGIN[origin]
    if origin == "ticket_flatten":
        return LOSS_LIMIT_LINE_YOU          # your own Flatten
    if source in _NOVA_SOURCES:
        return None
    return LOSS_LIMIT_LINE_YOU


def counted(account: str) -> tuple[bool, str | None]:
    """``(True, None)`` when ``account`` is counted now, else ``(False, why)``."""
    if account == "sim":
        from sim.mode import is_replay_desk, venue

        if venue() != "sim":
            return False, "Sim is counted only while the desk is on Sim at the live edge"
        if is_replay_desk():
            return False, "A Sim replay is not today: nothing is counted"
    return True, None


def _practice(account: str) -> Count:
    from loss_limit.state import day_start
    from practice.broker import for_venue
    from practice.fees import Fees

    broker = for_venue(account)
    broker.rollover()
    ledger = broker.ledger
    # The loss limit's day walks back over a weekend or holiday like Day P&L's (ADR 056 amendment 2026-10-27).
    start = day_start(float(broker.reference.now_ts()))
    fills: list[Fill] = []
    for row in ledger.closed_orders():
        if str(row.get("status")) != "Filled":
            continue
        ts = _num(row.get("fill_ts"))
        qty, price = _num(row.get("filled_qty")), _num(row.get("avg_fill_price"))
        if ts is None or ts < start or not qty or price is None:
            continue
        side = str(row.get("side") or "").upper()
        fills.append(Fill(symbol=str(row["symbol"]), shares=qty if side == "BUY" else -qty, price=price,
                          cost=Fees.from_dict(row.get("fees")).total, by=by_of(row), ts=ts))
    held = {str(r["symbol"]).upper(): Held(shares=float(r["qty"]), mark=_num(r.get("market_price")))
            for r in broker.positions()}
    return count(fills, held)


def _live_snapshot(account_id: str, start: float) -> tuple[list[Fill], dict[str, Held]]:
    """On the IB loop: today's stock executions for ``account_id`` and its stock positions."""
    from ibkr import client

    ib = client.get_ib()
    if ib is None:
        raise RuntimeError("IBKR is not ready")
    fills: list[Fill] = []
    for fill in list(ib.fills() or []):
        contract, execution = getattr(fill, "contract", None), getattr(fill, "execution", None)
        if getattr(contract, "secType", "STK") != "STK" or execution is None:
            continue
        if str(getattr(execution, "acctNumber", "") or "") not in ("", account_id):
            continue
        when = getattr(execution, "time", None) or getattr(fill, "time", None)
        if when is None or when.timestamp() < start:
            continue
        shares, price = _num(getattr(execution, "shares", None)), _num(getattr(execution, "price", None))
        if not shares or price is None:
            continue
        side = str(getattr(execution, "side", "") or "").upper()
        report = getattr(fill, "commissionReport", None)
        cost = _num(getattr(report, "commission", None)) if getattr(report, "execId", "") else None
        # Yours: a bot never trades Live (Invariant #7).
        fills.append(Fill(symbol=str(contract.symbol), shares=shares if side in ("BOT", "BUY") else -shares,
                          price=price, cost=cost, by=LOSS_LIMIT_LINE_YOU, ts=when.timestamp()))
    held: dict[str, Held] = {}
    for item in list(ib.portfolio(account_id) or []):
        if getattr(item.contract, "secType", "STK") != "STK":
            continue
        mark = _num(item.marketPrice)
        held[str(item.contract.symbol).upper()] = Held(shares=float(item.position),
                                                       mark=mark if mark and mark > 0 else None)
    return fills, held


def _live(now: float) -> Count:
    from ibkr import client
    from ibkr.loop_supervisor import call_on_ib
    from loss_limit.state import day_start

    if not (client.is_enabled() and client.is_ready()):
        return Count(pnl=None, unknown="IBKR is not connected, so Live cannot be counted")
    account_id = client.account_id()
    if not account_id:
        return Count(pnl=None, unknown="IBKR has not named the account, so Live cannot be counted")
    start = day_start(now)
    fills, held = call_on_ib(lambda: _live_snapshot(account_id, start), _IB_READ_TIMEOUT_SEC,
                             label="loss_limit.live")
    return count(fills, held)


def read(account: str, now: float) -> Count:
    """``account``'s count now; a ``Count`` with ``pnl`` None and ``unknown`` when it cannot be read."""
    ok, why = counted(account)
    if not ok:
        return Count(pnl=None, unknown=why)
    try:
        return _live(now) if account == "live" else _practice(account)
    except Exception as exc:
        logger.warning("LOSS LIMIT: %s could not be counted", account, exc_info=True)
        return Count(pnl=None, unknown=f"{account.capitalize()} could not be read ({type(exc).__name__})")
