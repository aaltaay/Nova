"""The pre-registered read-out that unlocks Strategy on Live, per setup (ADR 027, ADR 031).

Bot-Trading-Plan §2g: read the scoreboard once ``SETUPS_READOUT_MIN_GO``
triggered first-pullback setups had the tape at go at the trigger. It passes
when their average net R is above ``SETUPS_READOUT_MIN_NET_R`` and above the
average of the triggered setups whose tape was blind or wait over the same
days. No pass by ``SETUPS_READOUT_FAIL_GO`` go setups -> failed. Scores, not
fills (the research exit rules on every armed setup, ``summary.net_r``).

``evaluate`` is pure; ``current`` reads ``setups.db`` through the engine's store
and caches the answer for ``SETUPS_READOUT_CACHE_SEC`` (owner: this module,
in memory only; invalidation: the TTL, per template and revision). A store
that is not open reads ``unavailable`` -- the gate stays closed, never guessed
open.

ADR 029: the read-out is per template. ``current()`` judges a setup's template
in play on its own rows -- the ones its exact rules (``template_id`` and
``template_rev``) armed -- so editing a template starts its evidence over.

ADR 031: every setup with a scanner has its own read-out, the same rule over its
own first-of-the-day kind (``SETUPS_READOUT_KINDS``: the first pullback, the
first bull flag, the first flat-top breakout, red to green).
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
    SETUPS_READOUT_KINDS,
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
_cached: dict[tuple[str, str, int], tuple[float, dict[str, Any]]] = {}


def _rules(template: dict[str, Any] | None = None, kind: str = SETUPS_READOUT_KIND) -> dict[str, Any]:
    return {"kind": kind, "min_go": SETUPS_READOUT_MIN_GO,
            "fail_go": SETUPS_READOUT_FAIL_GO, "min_net_r": SETUPS_READOUT_MIN_NET_R,
            "template": template}


def _block(rows: list[dict]) -> dict[str, Any]:
    s = stats(rows)
    return {key: s[key] for key in ("triggered", "scored", "win_pct", "avg_net_r")}


def evaluate(rows: Iterable[dict], template: dict[str, Any] | None = None,
             kind: str = SETUPS_READOUT_KIND) -> dict[str, Any]:
    """The read-out over ``rows`` (one template's): ``{state, passed, go, control, rules, reason}``."""
    pool = sorted((r for r in rows if r.get("kind") == kind and r.get("triggered_at")),
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
            "go": go_block, "control": control_block, "rules": _rules(template, kind)}


def unavailable(reason: str, template: dict[str, Any] | None = None, kind: str = SETUPS_READOUT_KIND) -> dict[str, Any]:
    empty = {"triggered": 0, "scored": 0, "win_pct": None, "avg_net_r": None}
    return {"state": SETUPS_READOUT_UNAVAILABLE, "passed": False, "reason": reason,
            "go": dict(empty), "control": dict(empty), "rules": _rules(template, kind)}


def _in_play(setup: str) -> Any:
    from setup_templates.store import get_store

    return get_store().in_play(setup)


def current(*, now: float | None = None, template: Any = None, setup: str | None = None) -> dict[str, Any]:
    """The read-out of ``template`` (default: ``setup``'s template in play -- the first
    pullback's when neither is named), cached briefly."""
    from constants_bot import BOT_SETUP_FIRST_PULLBACK

    now = time.time() if now is None else now
    setup = getattr(template, "setup", None) or setup or BOT_SETUP_FIRST_PULLBACK
    kind = SETUPS_READOUT_KINDS.get(setup, SETUPS_READOUT_KIND)
    try:
        t = template if template is not None else _in_play(setup)
    except Exception as exc:
        logger.warning("setup read-out: the template in play could not be read", exc_info=True)
        return unavailable(f"the template in play could not be read: {exc}", kind=kind)
    stamp = {"id": t.id, "rev": int(t.rev), "name": t.name}
    key = (setup, t.id, int(t.rev))
    with _lock:
        hit = _cached.get(key)
        if hit is not None and now - hit[0] < SETUPS_READOUT_CACHE_SEC:
            return hit[1]
    try:
        from setup_scanner.engine import get_engine

        eng = get_engine()
        store = eng.store
        if store is None:
            out = unavailable(eng.store_error or "the scoreboard is not open yet", stamp, kind)
        else:
            out = evaluate(store.rows(setup_type=setup, template_id=t.id, template_rev=int(t.rev)), stamp, kind)
    except Exception as exc:
        logger.warning("setup read-out: scoreboard read failed", exc_info=True)
        out = unavailable(f"scoreboard read failed: {exc}", stamp, kind)
    with _lock:
        _cached[key] = (now, out)
    return out


def reset_for_tests() -> None:
    with _lock:
        _cached.clear()
