"""Pure scanner L1 stream-slot planner (tab first, then HOD)."""
from __future__ import annotations

from typing import Any

from constants import (
    IBKR_L1_ACTIVE_TAB_MAX,
    IBKR_L1_STREAM_BUDGET,
    IBKR_L1_STREAM_RESERVE,
)


def _budget_for_streams() -> int:
    return max(1, int(IBKR_L1_STREAM_BUDGET) - int(IBKR_L1_STREAM_RESERVE))


def plan_stream_symbols(
    tab_symbols: list[str],
    hod_symbols: list[str],
    *,
    budget: int | None = None,
    tab_max: int = IBKR_L1_ACTIVE_TAB_MAX,
) -> dict[str, Any]:
    """Pure planner: reserve tab slots first, then HOD, dedupe, reject overflow."""
    cap = int(budget if budget is not None else _budget_for_streams())
    tab_cap = max(0, min(int(tab_max), cap))
    tab: list[str] = []
    seen: set[str] = set()
    for raw in tab_symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        tab.append(sym)
        if len(tab) >= tab_cap:
            break
    rejected: list[str] = []
    for raw in tab_symbols[len(tab):]:
        sym = (raw or "").strip().upper()
        if sym and sym not in seen:
            rejected.append(sym)

    hod_slots = max(0, cap - len(tab))
    hod: list[str] = []
    for raw in hod_symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        if len(hod) >= hod_slots:
            rejected.append(sym)
            continue
        seen.add(sym)
        hod.append(sym)

    return {
        "tab": tab,
        "hod": hod,
        "combined": tab + [s for s in hod if s not in tab],
        "rejected": rejected,
        "budget": cap,
    }
