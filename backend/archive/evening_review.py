"""
Evening review — compare replay decisions vs a simple forward price heuristic (P9).

For each BUY/WAIT decision with a ticket entry, look ahead ``N`` minutes in
archived 1m bars and score a crude outcome. Emits a versioned findings dict.
"""
from __future__ import annotations

from typing import Any

from archive.replay import archive_bar_to_chart, load_table_rows, replay_day
from constants import (
    ARCHIVE_EVENING_REVIEW_HORIZON_MIN,
    ARCHIVE_EVENING_REVIEW_VERSION,
    NOVA_OS_DECISION_BUY,
    NOVA_OS_DECISION_WAIT,
)


def _bars_by_symbol(session_date: str, cold_dir=None) -> dict[str, list[dict[str, Any]]]:
    rows = load_table_rows(session_date, "bars_1m", cold_dir=cold_dir)
    by: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue
        by.setdefault(sym, []).append(archive_bar_to_chart(row))
    for series in by.values():
        series.sort(key=lambda b: float(b.get("ts") or 0))
    return by


def _outcome_for_decision(
    decision: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    horizon_min: int,
) -> dict[str, Any]:
    """Simple heuristic: price N minutes after last bar vs ticket entry."""
    ticket = decision.get("ticket") or {}
    entry = ticket.get("entry") or ticket.get("entry_price")
    stop = ticket.get("stop") or ticket.get("stop_price")
    target = ticket.get("target") or ticket.get("target_price")
    verdict = decision.get("decision")

    if not bars:
        return {
            "status": "no_bars",
            "horizon_min": horizon_min,
            "pnl_pct": None,
            "hit": None,
        }

    last_ts = float(bars[-1].get("ts") or 0)
    # Use last available bar as decision time for replay (end-of-series).
    horizon_sec = horizon_min * 60
    # Prefer a bar near the end; look for close after decision point.
    # Replay decisions are end-of-day snapshots — compare last close to
    # close ``horizon_min`` bars earlier when possible.
    if len(bars) > horizon_min:
        ref = bars[-(horizon_min + 1)]
        fwd = bars[-1]
        ref_px = float(ref.get("c") or 0)
        fwd_px = float(fwd.get("c") or 0)
    else:
        ref_px = float(entry) if entry else float(bars[0].get("c") or 0)
        fwd_px = float(bars[-1].get("c") or 0)

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
        "forward_price": fwd_px,
        "pnl_pct": round(pnl_pct, 4) if pnl_pct is not None else None,
        "hit": hit,
        "aligned_with_decision": aligned,
        "decision_ts": last_ts,
    }


def evening_review(
    session_date: str,
    *,
    cold_dir=None,
    horizon_min: int = ARCHIVE_EVENING_REVIEW_HORIZON_MIN,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Run replay + outcome heuristic; return versioned findings."""
    replay = replay_day(session_date, cold_dir=cold_dir, symbols=symbols)
    by_sym = _bars_by_symbol(session_date, cold_dir=cold_dir)

    findings: list[dict[str, Any]] = []
    aligned = 0
    scored = 0
    for dec in replay.get("decisions") or []:
        sym = str(dec.get("symbol", "")).upper()
        outcome = _outcome_for_decision(
            dec,
            by_sym.get(sym, []),
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
            "outcome": outcome,
        })

    return {
        "version": ARCHIVE_EVENING_REVIEW_VERSION,
        "session_date": session_date,
        "horizon_min": horizon_min,
        "ok": bool(replay.get("ok")),
        "replay_errors": replay.get("errors") or [],
        "finding_count": len(findings),
        "scored_count": scored,
        "aligned_count": aligned,
        "alignment_rate": (aligned / scored) if scored else None,
        "findings": findings,
        "note": (
            "Heuristic only — forward N-minute close vs ticket entry. "
            "Not expectancy, not live-readiness proof."
        ),
    }
