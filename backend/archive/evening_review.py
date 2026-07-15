"""
Evening review — compare no-hindsight replay decisions vs a forward price
heuristic (P9).

For each symbol, walk the archived day (``replay.walk_day``) and take the
first BUY signal that would have fired (or, if none ever fired, the
decision at the day's final as-of step) — a genuine decision moment, never
one that peeked at bars after it. Outcome is then scored by looking
*forward* ``horizon_min`` minutes from that exact moment in the (necessarily
full, unsliced) archived bars. Looking forward to grade an already-made
decision is not hindsight bias; feeding decide() those same future bars
*before* it decided would be — this module now keeps the two strictly apart.

v1 (pre 2026-07-15) scored outcome by looking *backward* from the day's last
bar (``bars[-(horizon+1)]`` vs ``bars[-1]``), which had no connection to when
a decision was actually made, and its underlying replay fed decide() the
whole day at once. Both bugs are fixed here; ``ARCHIVE_EVENING_REVIEW_VERSION``
was bumped so findings are distinguishable.
"""
from __future__ import annotations

from typing import Any

from archive.replay import bars_by_symbol_for_day, walk_day
from constants import (
    ARCHIVE_EVENING_REVIEW_HORIZON_MIN,
    ARCHIVE_EVENING_REVIEW_MAX_SYMBOLS,
    ARCHIVE_EVENING_REVIEW_VERSION,
    ARCHIVE_REPLAY_WALK_STEP_MIN,
    NOVA_OS_DECISION_BUY,
    NOVA_OS_DECISION_WAIT,
)


def _first_buy_or_last_step(walk: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """The first BUY decision found while walking the day for ``symbol``, no
    lookahead involved (each step only saw bars up to its own as_of_ts); if
    none ever fired, fall back to the decision at the walk's final step."""
    last_seen: dict[str, Any] | None = None
    for step in walk.get("steps") or []:
        for dec in step.get("decisions") or []:
            if str(dec.get("symbol", "")).upper() != symbol:
                continue
            last_seen = dec
            if dec.get("decision") == NOVA_OS_DECISION_BUY:
                return dec
    return last_seen


def _outcome_for_decision(
    decision: dict[str, Any],
    full_day_bars: list[dict[str, Any]],
    *,
    as_of_ts: float | None,
    horizon_min: int,
) -> dict[str, Any]:
    """Forward-looking heuristic: price ~``horizon_min`` minutes *after*
    ``as_of_ts`` vs ticket entry (or the price decide() actually saw at
    ``as_of_ts`` when there's no ticket)."""
    ticket = decision.get("ticket") or {}
    entry = ticket.get("entry") or ticket.get("entry_price")
    stop = ticket.get("stop") or ticket.get("stop_price")
    target = ticket.get("target") or ticket.get("target_price")
    verdict = decision.get("decision")

    if not full_day_bars or as_of_ts is None:
        return {
            "status": "no_bars",
            "horizon_min": horizon_min,
            "pnl_pct": None,
            "hit": None,
            "decision_ts": as_of_ts,
        }

    ref_bars = [b for b in full_day_bars if float(b.get("ts") or 0) <= as_of_ts]
    forward_bars = [b for b in full_day_bars if float(b.get("ts") or 0) > as_of_ts]
    if not forward_bars:
        return {
            "status": "no_forward_bars",
            "horizon_min": horizon_min,
            "pnl_pct": None,
            "hit": None,
            "decision_ts": as_of_ts,
        }

    target_ts = as_of_ts + horizon_min * 60
    within_horizon = [b for b in forward_bars if float(b.get("ts") or 0) <= target_ts]
    fwd_bar = within_horizon[-1] if within_horizon else forward_bars[-1]
    fwd_px = float(fwd_bar.get("c") or 0)

    ref_px = float(ref_bars[-1].get("c") or 0) if ref_bars else fwd_px
    entry_px = float(entry) if entry else ref_px
    pnl_pct = ((fwd_px - entry_px) / entry_px * 100.0) if entry_px else None

    hit: str | None = None
    if entry_px and stop is not None and target is not None and pnl_pct is not None:
        # Crude: if forward move toward target without considering path
        if fwd_px >= float(target):
            hit = "target"
        elif fwd_px <= float(stop):
            hit = "stop"
        else:
            hit = "open"
    elif pnl_pct is not None:
        hit = "up" if pnl_pct > 0 else ("down" if pnl_pct < 0 else "flat")

    aligned = None
    if verdict == NOVA_OS_DECISION_BUY and pnl_pct is not None:
        aligned = pnl_pct > 0
    elif verdict == NOVA_OS_DECISION_WAIT and pnl_pct is not None:
        aligned = pnl_pct <= 0  # waiting was "right" if price didn't rally

    return {
        "status": "scored",
        "horizon_min": horizon_min,
        "entry": entry_px,
        "reference_price": ref_px,
        "forward_price": fwd_px,
        "pnl_pct": round(pnl_pct, 4) if pnl_pct is not None else None,
        "hit": hit,
        "aligned_with_decision": aligned,
        "decision_ts": as_of_ts,
        "forward_ts": float(fwd_bar.get("ts") or 0),
    }


def evening_review(
    session_date: str,
    *,
    cold_dir=None,
    horizon_min: int = ARCHIVE_EVENING_REVIEW_HORIZON_MIN,
    symbols: list[str] | None = None,
    step_min: float = ARCHIVE_REPLAY_WALK_STEP_MIN,
    max_symbols: int = ARCHIVE_EVENING_REVIEW_MAX_SYMBOLS,
) -> dict[str, Any]:
    """Walk the day no-hindsight, pick each symbol's real decision moment,
    score it forward, and return versioned findings."""
    walk = walk_day(
        session_date,
        cold_dir=cold_dir,
        symbols=symbols,
        max_symbols=max_symbols,
        step_min=step_min,
    )
    by_sym_full = bars_by_symbol_for_day(session_date, cold_dir=cold_dir)

    findings: list[dict[str, Any]] = []
    aligned = 0
    scored = 0
    for sym in walk.get("symbols") or []:
        dec = _first_buy_or_last_step(walk, sym)
        if dec is None:
            continue
        as_of_ts = (dec.get("replay") or {}).get("as_of_ts")
        outcome = _outcome_for_decision(
            dec,
            by_sym_full.get(sym, []),
            as_of_ts=as_of_ts,
            horizon_min=horizon_min,
        )
        if outcome.get("status") == "scored":
            scored += 1
            if outcome.get("aligned_with_decision") is True:
                aligned += 1
        findings.append({
            "symbol": sym,
            "decision": dec.get("decision"),
            "reason_codes": dec.get("reason_codes"),
            "confidence": dec.get("confidence"),
            "ticket": dec.get("ticket"),
            "as_of_ts": as_of_ts,
            "outcome": outcome,
        })

    return {
        "version": ARCHIVE_EVENING_REVIEW_VERSION,
        "session_date": session_date,
        "horizon_min": horizon_min,
        "step_min": step_min,
        "ok": bool(walk.get("ok")),
        "walk_step_count": walk.get("step_count", 0),
        "finding_count": len(findings),
        "scored_count": scored,
        "aligned_count": aligned,
        "alignment_rate": (aligned / scored) if scored else None,
        "findings": findings,
        "note": (
            "No-hindsight: each finding's decision only saw bars up to its own "
            "as_of_ts (walk_day); outcome is scored forward from that same "
            "as_of_ts. Heuristic only — not expectancy, not live-readiness proof."
        ),
    }
