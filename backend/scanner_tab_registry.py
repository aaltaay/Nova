"""Per-client displayed scanner tables for IBKR L1 streaming.

A desk renders more than one scanner table at a time — the main tab plus the
scanner dock roster — so each client declares the *set* of tables it is
showing. A single dominant string could not express "main = Gappers (frozen)
+ dock = Gainers (live)": the hint named the frozen table, ``symbols_for_tab``
correctly returned [] (ADR 008), and the active-tab set emptied, which
silently stopped every ``price_patch`` for every table.
"""
from __future__ import annotations

from typing import Any

from fastapi import WebSocket

ALLOWED_TABS = frozenset({
    "gappers",
    "gainers",
    "losers",
    "afterhours",
    "catalysts",
    "none",
})

_client_tabs: dict[int, tuple[str, ...]] = {}


def _normalize(tabs: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Lowercase, drop unknown/'none', dedupe while preserving caller order."""
    out: list[str] = []
    for raw in tabs:
        tab = (str(raw) or "").strip().lower()
        if tab not in ALLOWED_TABS or tab == "none":
            continue
        if tab not in out:
            out.append(tab)
    return tuple(out)


def set_tabs(websocket: WebSocket, tabs: list[str] | tuple[str, ...]) -> list[str]:
    """Record every scanner table this client is displaying."""
    normalized = _normalize(tabs)
    _client_tabs[id(websocket)] = normalized
    return list(normalized)


def set_tab(websocket: WebSocket, tab: str) -> str:
    """Single-table hint (older clients). Returns the stored tab or 'none'."""
    stored = set_tabs(websocket, [tab])
    return stored[0] if stored else "none"


def clear(websocket: WebSocket) -> None:
    _client_tabs.pop(id(websocket), None)


def get_active_tables() -> list[str]:
    """Union of displayed tables across clients, most-demanded first.

    Order is deterministic (count desc, then name) so the L1 planner fills its
    active-tab budget from the table the most desks are actually watching.
    """
    counts: dict[str, int] = {}
    for tabs in _client_tabs.values():
        for tab in tabs:
            counts[tab] = counts.get(tab, 0) + 1
    if not counts:
        return []
    return [tab for tab, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def get_dominant_tab() -> str:
    """Most-demanded single table; 'none' when no client shows a scanner table."""
    tables = get_active_tables()
    return tables[0] if tables else "none"


def client_count() -> int:
    return len(_client_tabs)


def snapshot() -> dict[str, Any]:
    return {
        "clients": client_count(),
        "tables": get_active_tables(),
        "dominant_tab": get_dominant_tab(),
        "tabs": {key: list(tabs) for key, tabs in _client_tabs.items()},
    }
