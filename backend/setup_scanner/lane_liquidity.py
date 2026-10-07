"""Whether a lane's armed setup is too thin to trade (operator decision 2026-10-01; rule in ``liquidity.py``).

A lane reads its active setup's liquidity when the setup arms, when it first comes near, at each closed
minute while it is armed or near, and at its trigger -- where the reading freezes on the row and is
stored with it (``setups.db`` ``liquidity``). Every change of the reading's verdict is journalled
(``armed`` / ``near`` / ``triggered`` lines carry it, a ``liquidity`` line between them), so the eyes'
playback draws the card the lane showed. A thin setup never proposes and its trigger tells the bot so
(``trade_verdict``); it is still scored -- outside the read-out -- so the rule itself can be checked.

The reading uses the lane's own one-minute bars, the day volume in its pillars, the host's newest fresh
Level 2 book (a short's walk is through the bids, ADR 049) and the desk's risk per trade (``host.risk_usd``; a replay host has none, so it never judges
the book). Owner: ``setup_scanner/lane.py`` (the row holds the reading; nothing is kept here).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_setups import SETUPS_BAR_SEC, SETUPS_THIN_PACE_SEC, TAPE_GATE_STALE_BOOK_SEC
from setup_scanner import liquidity, tape_gap
from setup_scanner.lane_view import WATCH_STATES

logger = logging.getLogger(__name__)


def _book(host: Any, sym: str, now: float) -> dict | None:
    """The newest Level 2 book no older than the tape gate's stale limit, with more than the inside."""
    newest = None
    for ts, book in host.tape_books(sym) or []:
        if book and ts <= now + 1e-6 and now - ts <= TAPE_GATE_STALE_BOOK_SEC and (newest is None or ts >= newest[0]):
            newest = (ts, book)
    if newest is None or newest[1].get("l1_fallback"):
        return None
    return newest[1]


def _risk_usd(host: Any) -> float | None:
    ask = getattr(host, "risk_usd", None)
    if ask is None:
        return None
    try:
        return ask()
    except Exception:
        logger.warning("setup scanner: the desk's risk per trade could not be read", exc_info=True)
        return None


def reading(lane: Any, sym: str, now: float, risk: Any) -> dict[str, Any]:
    """The liquidity of ``sym`` at ``now`` for a setup risking ``risk`` a share."""
    host = lane.host
    bars = lane.bars.get(sym) or []
    pillars = host.pillars(sym, now) or {}
    unknown: dict[str, str] = {}
    end = float(int(now // SETUPS_BAR_SEC) * SETUPS_BAR_SEC)
    pace: float | None = None
    gaps = getattr(host, "feed_gaps", None)
    gap = tape_gap.touching(gaps(now), end - SETUPS_THIN_PACE_SEC, end) if gaps is not None else None
    if gap is not None:
        unknown["pace"] = "the IBKR feed had a gap in the last 5 minutes"
    elif not bars:
        unknown["pace"] = "no minute bars yet"
    else:
        pace = liquidity.pace_dollars(bars, end)
    day = liquidity.day_dollars(pillars.get("volume"), bars, end, pillars.get("price"))
    book = _book(host, sym, now)
    qty = liquidity.size_for(_risk_usd(host), risk)
    walked = None
    if book is None:
        unknown["book"] = "Nova holds no fresh Level 2 book for it"
    elif qty < 1:
        unknown["book"] = "no risk per trade to size the fill by"
    else:
        short = getattr(lane.p, "short", False)    # ADR 049: a short sells into the bids
        walked = liquidity.walk_bids(book.get("bids") or [], qty) if short else liquidity.walk(book.get("asks") or [], qty)
        if walked is None:
            unknown["book"] = "the book shows no bid" if short else "the book shows no offer"
    return liquidity.judge(day=day, pace=pace, now=now, book=walked, risk=risk, unknown=unknown)


def stamp(lane: Any, sym: str, row: dict, now: float) -> dict[str, Any]:
    """Read and keep the reading on the row; the caller journals it with its own line."""
    row["liquidity"] = reading(lane, sym, now, row.get("risk"))
    return row["liquidity"]


def refresh(lane: Any, sym: str, now: float) -> None:
    """At a closed minute: re-read the active armed or near setup; a changed verdict is kept and journalled."""
    sid = lane.active_id.get(sym)
    row = lane.rows.get(sid) if sid else None
    det = lane.det.get(sym)
    if (row is None or det is None or sid in lane.filtered or row.get("triggered_at")
            or det.state not in WATCH_STATES or row.get("leg_t") != det.view().get("setup_key")):
        return
    fresh = reading(lane, sym, now, row.get("risk"))
    if liquidity.same(fresh, row.get("liquidity")):
        return
    row["liquidity"] = fresh
    lane.journal("liquidity", sym, setup_id=sid, liquidity=fresh)
    lane.host.save(row)


def thin(row: dict | None) -> bool:
    return liquidity.is_thin((row or {}).get("liquidity"))

