"""Scoreboard summary: what the armed setups did, split the ways that answer
the question the scanner exists for -- does the tape gate turn a losing bar
shape into a winning trade? (ADR 022)

Pure: rows in, numbers out. Every split carries its own count so a small
sample is visible as small. ``flow_at_trigger`` splits by the tape flow's label
at the trigger (ADR 034): does a burst into the trigger beat a flush into it?
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from constants_setups import (
    SETUP_OUTCOME_OPEN,
    SETUP_OUTCOME_STOP_FIRST,
    SETUP_OUTCOME_TARGET_FIRST,
)

ET = ZoneInfo("America/New_York")
SLIPPAGE_PER_FILL = 0.01   # the research ladder's base cost, per fill
RTH_OPEN = dtime(9, 30)
# Exits after half came off at target 1: three fills (in, half, the rest), not two.
THREE_FILL_EXITS = frozenset({"ema", "breakeven", "flush_runner", "flush_stop_runner"})


def _session(row: dict) -> str:
    ts = row.get("armed_at")
    if not ts:
        return "unknown"
    return "premarket" if datetime.fromtimestamp(float(ts), ET).time() < RTH_OPEN else "regular"


def _tape(row: dict) -> str:
    tape = row.get("trigger_tape") or {}
    return str(tape.get("verdict") or "none") if isinstance(tape, dict) else "none"


def _flow(row: dict) -> str:
    tape = row.get("trigger_tape") or {}
    flow = tape.get("flow") if isinstance(tape, dict) else None
    return str(flow.get("label") or "none") if isinstance(flow, dict) else "none"


def net_r(row: dict) -> float | None:
    r, risk = row.get("bar_r"), row.get("risk")
    if r is None or not risk:
        return None
    fills = 3 if row.get("bar_exit_reason") in THREE_FILL_EXITS else 2
    return round(float(r) - fills * SLIPPAGE_PER_FILL / float(risk), 3)


def _stats(rows: list[dict]) -> dict[str, Any]:
    trig = [r for r in rows if r.get("triggered_at")]
    scored = [r for r in trig if r.get("bar_r") is not None]
    def avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 3) if vals else None
    def r_of(r, key):
        v, risk = r.get(key), r.get("risk")
        return float(v) / float(risk) if v is not None and risk else None
    return {
        "armed": len(rows),
        "triggered": len(trig),
        "trigger_rate": round(len(trig) / len(rows), 3) if rows else None,
        "target_first": sum(1 for r in trig if r.get("outcome") == SETUP_OUTCOME_TARGET_FIRST),
        "stop_first": sum(1 for r in trig if r.get("outcome") == SETUP_OUTCOME_STOP_FIRST),
        "open": sum(1 for r in trig if r.get("outcome") in (None, SETUP_OUTCOME_OPEN)),
        "scored": len(scored),
        "win_pct": round(100 * sum(1 for r in scored if float(r["bar_r"]) > 0) / len(scored), 1) if scored else None,
        "avg_r": avg(float(r["bar_r"]) for r in scored),
        "avg_net_r": avg(net_r(r) for r in scored),
        "avg_mfe_r": avg(r_of(r, "mfe") for r in trig),
        "avg_mae_r": avg(r_of(r, "mae") for r in trig),
    }


def stats(rows: Iterable[dict]) -> dict[str, Any]:
    """One stats block over ``rows`` (the read-out pools blind and wait this way,
    never by averaging two group averages)."""
    return _stats(list(rows))


def tape_at_trigger(row: dict) -> str:
    return _tape(row)


def summarize(rows: Iterable[dict]) -> dict[str, Any]:
    rows = list(rows)
    out: dict[str, Any] = {"all": _stats(rows), "by": {}}
    for name, key in (("tape_at_trigger", _tape), ("flow_at_trigger", _flow),
                      ("grade", lambda r: r.get("grade") or "?"),
                      ("session", _session), ("kind", lambda r: r.get("kind") or "?")):
        groups: dict[str, list[dict]] = {}
        for r in rows:
            groups.setdefault(key(r), []).append(r)
        out["by"][name] = {k: _stats(v) for k, v in sorted(groups.items())}
    return out
