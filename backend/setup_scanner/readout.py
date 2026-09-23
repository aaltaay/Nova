"""The pre-registered read-out that unlocks Strategy for the first pullback (ADR 027).

Bot-Trading-Plan §2g: read the scoreboard once ``SETUPS_READOUT_MIN_GO``
triggered first-pullback setups had the tape at go at the trigger. It passes
when their average net R is above ``SETUPS_READOUT_MIN_NET_R`` and above the
average of the triggered setups whose tape was blind or wait over the same
days. No pass by ``SETUPS_READOUT_FAIL_GO`` go setups -> failed. Scores, not
fills (the research exit rules on every armed setup, ``summary.net_r``).

``evaluate`` is pure; ``current`` reads ``setups.db`` through the engine's store
and caches the answer for ``SETUPS_READOUT_CACHE_SEC`` (owner: this module,
in memory only; invalidation: the TTL). A store that is not open reads
``unavailable`` -- the gate stays closed, never guessed open.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Iterable

from constants_setups import (
    SETUPS_READOUT_CACHE_SEC,
    SETUPS_READOUT_COLLECTING,
    SETUPS_READOUT_FAIL_GO,
    SETUPS_READOUT_FAILED,
    SETUPS_READOUT_KIND,
    SETUPS_READOUT_MIN_GO,
    SETUPS_READOUT_MIN_NET_R,
    SETUPS_READOUT_NOT_PASSED,
    SETUPS_READOUT_PASSED,
    SETUPS_READOUT_UNAVAILABLE,
    TAPE_VERDICT_BLIND,
    TAPE_VERDICT_GO,
    TAPE_VERDICT_WAIT,
)
from setup_scanner.summary import stats, tape_at_trigger

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cached: tuple[float, dict[str, Any]] | None = None


def _rules() -> dict[str, Any]:
    return {"kind": SETUPS_READOUT_KIND, "min_go": SETUPS_READOUT_MIN_GO,
            "fail_go": SETUPS_READOUT_FAIL_GO, "min_net_r": SETUPS_READOUT_MIN_NET_R}


def _block(rows: list[dict]) -> dict[str, Any]:
    s = stats(rows)
    return {key: s[key] for key in ("triggered", "scored", "win_pct", "avg_net_r")}


def evaluate(rows: Iterable[dict]) -> dict[str, Any]:
    """The read-out over every scoreboard row: ``{state, passed, go, control, rules, reason}``."""
    pool = sorted((r for r in rows if r.get("kind") == SETUPS_READOUT_KIND and r.get("triggered_at")),
                  key=lambda r: float(r["triggered_at"]))
    go = [r for r in pool if tape_at_trigger(r) == TAPE_VERDICT_GO]
    control = [r for r in pool if tape_at_trigger(r) in (TAPE_VERDICT_BLIND, TAPE_VERDICT_WAIT)]
    if len(go) > SETUPS_READOUT_FAIL_GO:
        # Pre-registered: judged on the first FAIL_GO go setups and the control
        # over the same stretch -- waiting longer never turns a fail into a pass.
        go = go[:SETUPS_READOUT_FAIL_GO]
        last = float(go[-1]["triggered_at"])
        control = [r for r in control if float(r["triggered_at"]) <= last]
    go_block, control_block = _block(go), _block(control)
    go_r, control_r = go_block["avg_net_r"], control_block["avg_net_r"]
    n = go_block["triggered"]
    if n < SETUPS_READOUT_MIN_GO:
        state, reason = SETUPS_READOUT_COLLECTING, f"{n} of {SETUPS_READOUT_MIN_GO} go setups triggered"
    elif go_r is None:
        state, reason = SETUPS_READOUT_COLLECTING, "the go setups are not scored yet"
    elif control_r is None:
        state, reason = SETUPS_READOUT_COLLECTING, "no scored blind / wait setup to compare with yet"
    elif go_r > SETUPS_READOUT_MIN_NET_R and go_r > control_r:
        state, reason = SETUPS_READOUT_PASSED, (
            f"go {go_r:+.2f}R over {n} setups beats +{SETUPS_READOUT_MIN_NET_R:.2f}R and blind / wait {control_r:+.2f}R")
    else:
        failed = n >= SETUPS_READOUT_FAIL_GO
        state = SETUPS_READOUT_FAILED if failed else SETUPS_READOUT_NOT_PASSED
        reason = (f"go {go_r:+.2f}R over {n} setups; needs above +{SETUPS_READOUT_MIN_NET_R:.2f}R "
                  f"and above blind / wait {control_r:+.2f}R")
    return {"state": state, "passed": state == SETUPS_READOUT_PASSED, "reason": reason,
            "go": go_block, "control": control_block, "rules": _rules()}


def unavailable(reason: str) -> dict[str, Any]:
    empty = {"triggered": 0, "scored": 0, "win_pct": None, "avg_net_r": None}
    return {"state": SETUPS_READOUT_UNAVAILABLE, "passed": False, "reason": reason,
            "go": dict(empty), "control": dict(empty), "rules": _rules()}


def current(*, now: float | None = None) -> dict[str, Any]:
    """The read-out from ``setups.db`` (every day), cached briefly."""
    global _cached
    now = time.time() if now is None else now
    with _lock:
        if _cached is not None and now - _cached[0] < SETUPS_READOUT_CACHE_SEC:
            return _cached[1]
    try:
        from setup_scanner.engine import get_engine

        eng = get_engine()
        store = eng.store
        if store is None:
            out = unavailable(eng.store_error or "the scoreboard is not open yet")
        else:
            out = evaluate(store.rows())
    except Exception as exc:
        logger.warning("setup read-out: scoreboard read failed", exc_info=True)
        out = unavailable(f"scoreboard read failed: {exc}")
    with _lock:
        _cached = (now, out)
    return out


def reset_for_tests() -> None:
    global _cached
    with _lock:
        _cached = None
