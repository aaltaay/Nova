"""Which Trader tabs the operator can see, from the focus sensor (ADR 033), for line lending (ADR 044).

A tab is **in front** when a fresh, visible, not-minimized window shows it: the
Trader page's active tab, a pop-out's, or the Trader slot beside the Desk board
(``symbol_source: "trader_tab"``). A window behind another app but not minimized
still shows its tab: in front. A tab is **known** when a fresh window lists it
among its Trader tabs. With no fresh window report the answer is unknown, and an
unknown answer lends nothing (``known`` False).

Pure over ``sensors.focus_store.resolve()``'s answer, plus a reader.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TRADER_PAGE = "trader"
TRADER_TAB_SOURCE = "trader_tab"


@dataclass(frozen=True)
class FocusRead:
    known: bool
    front: frozenset[str] = field(default_factory=frozenset)
    tabs: frozenset[str] = field(default_factory=frozenset)
    # symbol -> the newest moment a window showed it (the focus sensor's recent list).
    last_shown: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def is_front(self, symbol: str) -> bool | None:
        """True / False when the focus is known, None when it is not."""
        return (symbol in self.front) if self.known else None


def _sym(raw: Any) -> str | None:
    text = str(raw or "").strip().upper()
    return text or None


def from_resolved(resolved: dict[str, Any]) -> FocusRead:
    windows = [w for w in resolved.get("windows") or [] if isinstance(w, dict)]
    if not windows:
        return FocusRead(known=False)
    front: set[str] = set()
    tabs: set[str] = set()
    for w in windows:
        sym = _sym(w.get("symbol"))
        shows_tab = sym is not None and (w.get("page") == TRADER_PAGE or w.get("symbol_source") == TRADER_TAB_SOURCE)
        if shows_tab:
            tabs.add(sym)
        tabs.update(s for s in (_sym(t) for t in w.get("trader_tabs") or []) if s)
        if shows_tab and w.get("visible") and not w.get("minimized"):
            front.add(sym)
    last: dict[str, float] = {}
    for row in resolved.get("recent") or []:
        sym = _sym((row or {}).get("symbol"))
        ts = (row or {}).get("ts")
        if sym and isinstance(ts, (int, float)):
            last[sym] = max(last.get(sym, 0.0), float(ts))
    return FocusRead(known=True, front=frozenset(front), tabs=frozenset(tabs), last_shown=last)


def read(now: float | None = None) -> FocusRead:
    """The focus now; unknown (with the reason) when the sensor cannot be read."""
    from sensors import focus_store

    try:
        return from_resolved(focus_store.resolve(time.time() if now is None else now))
    except Exception as exc:
        logger.warning("line lending: the focus sensor could not be read -- no line is lent", exc_info=True)
        return FocusRead(known=False, error=f"the focus sensor could not be read ({type(exc).__name__})")
