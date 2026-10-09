"""Every IBKR session that becomes READY is reconciled with what Nova recorded before it.

A reconnect inside this process builds a new ``IB()``, and what happened while the socket was down
reaches it only as answers to its connect-time requests, never as live events. So on every READY,
on the IB loop right after READY's own hooks:

1. the fills the session read back that no handler heard (``ibkr.session_fills.take_unheard``) go to
   their watches as if heard live, or are claimed (``execution.fill_claims``; a liquidation is loud);
2. IBKR's positions are compared with the last ones it reported: a position that moved by more than
   those fills explain is loud (``ibkr.unclaimed.note_position_gap``);
3. after the first READY -- a reconnect inside this process -- the ledger sweep runs again over this
   process's own rows too, closing them only on the broker's evidence (``execution.startup_sweep``).

Between READYs, each position update catches up fills no handler heard, so an IBKR liquidation is
said as it lands rather than at the next reconnect.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from execution import fill_claims, telemetry
from ibkr import session_fills, unclaimed

logger = logging.getLogger(__name__)

_ready_seen = False


def on_ready(ib: Any) -> None:
    """On the IB loop, from ``ibkr.session_usable`` after READY. Never raises."""
    global _ready_seen
    reconnect = _ready_seen
    _ready_seen = True
    try:
        session_fills.wire(ib, _on_position)
        asyncio.get_running_loop().call_soon(_run, ib, reconnect)
    except RuntimeError:
        _run(ib, reconnect)  # no running loop (tests)
    except Exception:
        logger.exception("execution: the READY reconcile could not be scheduled")


def _run(ib: Any, reconnect: bool) -> None:
    try:
        reconcile(ib, reconnect=reconnect)
    except Exception:
        logger.exception("execution: the READY reconcile failed -- this process's rows were not swept")


def _fills_and_positions(ib: Any) -> dict[str, Any]:
    """Steps 1 and 2. Raises when IBKR's fills or positions are unreadable: nothing is compared then."""
    before = session_fills.mirror()
    unheard = session_fills.take_unheard(ib)
    counts = fill_claims.catch_up(ib, unheard, telemetry._watches.get)
    fills_now = list(ib.fills() or [])
    after = session_fills.read_positions(ib)
    gaps = [] if before is None else session_fills.explain(before, after, fills_now)
    for gap in gaps:
        unclaimed.note_position_gap(gap)
    session_fills.remember(after, fills_now)
    return {"unheard": len(unheard), "claims": counts, "gaps": gaps}


def reconcile(ib: Any, *, reconnect: bool) -> dict[str, Any]:
    """Steps 1-3 above; returns what each found (for the log and tests). The sweep runs either way."""
    found: dict[str, Any] = {"unheard": None, "claims": None, "gaps": None, "swept": None}
    try:
        found.update(_fills_and_positions(ib))
    except Exception:
        logger.exception("execution: IBKR's fills or positions could not be read -- they were not compared")
    if reconnect:
        from execution.startup_sweep import run_startup_sweep

        found["swept"] = run_startup_sweep(include_current_boot=True)
    logger.info(
        "execution: READY reconcile (%s) -- unheard fills %s %s, position gaps %s",
        "reconnect" if reconnect else "first session", found["unheard"], found["claims"],
        None if found["gaps"] is None else len(found["gaps"]),
    )
    return found


def _on_position(ib: Any) -> None:
    """A position moved: a fill that came with it and no handler heard is claimed now."""
    unheard = session_fills.take_unheard(ib)
    if unheard:
        fill_claims.catch_up(ib, unheard, telemetry._watches.get)


def reset_for_tests() -> None:
    global _ready_seen
    _ready_seen = False
