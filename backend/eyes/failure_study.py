"""The study of setups that ended (ADR 036 amendment, operator ask 2026-09-29): every failed or faded
setup of the days asked, grouped by setup, end and reason, with what price did after each
(``eyes/aftermath.py``) -- "higher-high failures: 23, of which 14 ran over the high first". A faded
setup that never got past its leg is left out unless asked for (the chart does not draw it either).
Triggered setups are totalled beside them for comparison, from their own scores.

``study`` is pure over its inputs: the journal files, a bars reader and the clock. Read by
``tools/setup_failures.py``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from constants_setups import SETUP_OUTCOME_OPEN, SETUP_OUTCOME_STOP_FIRST, SETUP_OUTCOME_TARGET_FIRST
from eyes import aftermath
from eyes.episodes import END_FADED, END_FAILED, END_TRIGGERED, fold
from eyes.journal_day import JournalTail
from setup_scanner.bars import Bar

logger = logging.getLogger(__name__)
SCHEMA_VERSION = 1
FIRSTS = ("high", "low", "neither", "pending", "unknown")
OUTCOMES = (SETUP_OUTCOME_TARGET_FIRST, SETUP_OUTCOME_STOP_FIRST, SETUP_OUTCOME_OPEN)
BarsFn = Callable[[str, str], "list[Bar]"]


def drawn(ep: dict[str, Any]) -> bool:
    """A failed or faded setup the chart draws: a faded one that never got past its leg is not."""
    return ep["end"] == END_FAILED or (ep["end"] == END_FADED and ep["reached"] != "leg")


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _trades(rows: list[dict[str, Any] | None]) -> dict[str, Any]:
    kept = [t for t in rows if t]
    out: dict[str, Any] = {"n": len(kept), **{o: sum(1 for t in kept if t.get("outcome") == o) for o in OUTCOMES}}
    out["avg_bar_r"] = _avg([float(t["bar_r"]) for t in kept if t.get("bar_r") is not None])
    return out


def study(days: list[tuple[str, Path]], *, bars_fn: BarsFn, now: float, setup: str | None = None,
          symbol: str | None = None, include_legs: bool = False, listing: bool = False) -> dict[str, Any]:
    """Every day's ended setups, grouped by ``(setup_type, end, reason_key)``, most frequent first."""
    groups: dict[tuple, dict[str, Any]] = {}
    triggered: list[dict[str, Any] | None] = []
    listed: list[dict[str, Any]] = []
    missing: list[str] = []
    left_out = 0
    for date, path in days:
        eps = fold(JournalTail(path, date).read()).episodes()
        bars_by: dict[str, list[Bar] | None] = {}
        for ep in eps:
            if (setup and ep["setup_type"] != setup) or (symbol and ep["symbol"].upper() != symbol.upper()):
                continue
            if ep["end"] == END_TRIGGERED:
                triggered.append(ep.get("score"))
                continue
            if ep["end"] not in (END_FAILED, END_FADED):
                continue
            if not include_legs and not drawn(ep):
                left_out += 1
                continue
            sym = ep["symbol"]
            if sym not in bars_by:
                try:
                    bars_by[sym] = bars_fn(sym, date) or None
                except Exception:
                    logger.warning("setup failures: bars of %s on %s unread", sym, date, exc_info=True)
                    bars_by[sym] = None
                if bars_by[sym] is None:
                    missing.append(f"{sym} {date}")
            bars = bars_by[sym]
            ep["after"] = aftermath.after(ep, bars, now=now) if bars else None
            ep["date"] = date
            key = (ep["setup_type"], ep["end"], ep["reason_key"] or "")
            g = groups.setdefault(key, {"setup_type": key[0], "end": key[1], "reason_key": key[2] or None,
                                        "example": ep["reason"], "count": 0, "first": dict.fromkeys(FIRSTS, 0),
                                        "_trades": []})
            g["count"] += 1
            first = (ep["after"] or {}).get("first") or "unknown"
            g["first"][first] += 1
            g["_trades"].append((ep["after"] or {}).get("trade"))
            if listing:
                listed.append(ep)
    rows = []
    for g in sorted(groups.values(), key=lambda g: (-g["count"], g["setup_type"], g["reason_key"] or "")):
        rows.append({**{k: v for k, v in g.items() if k != "_trades"}, "trade": _trades(g["_trades"])})
    scored = [s for s in triggered if s]
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "generated_at": now, "dates": [d for d, _ in days],
        "filters": {"setup": setup, "symbol": symbol, "include_legs": include_legs},
        "ended": sum(g["count"] for g in rows), "left_out_legs": left_out, "missing_bars": missing,
        "groups": rows,
        "triggered": {"count": len(triggered), **{o: sum(1 for s in scored if s.get("outcome") == o) for o in OUTCOMES},
                      "avg_bar_r": _avg([float(s["bar_r"]) for s in scored if s.get("bar_r") is not None])},
    }
    if listing:
        out["episodes"] = listed
    return out
