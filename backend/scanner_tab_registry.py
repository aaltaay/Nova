"""Per-client active scanner tab hints for IBKR L1 streaming."""
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

_client_tabs: dict[int, str] = {}


def set_tab(websocket: WebSocket, tab: str) -> str:
    key = id(websocket)
    normalized = (tab or "none").strip().lower()
    if normalized not in ALLOWED_TABS:
        normalized = "none"
    _client_tabs[key] = normalized
    return normalized


def clear(websocket: WebSocket) -> None:
    _client_tabs.pop(id(websocket), None)


def get_dominant_tab() -> str:
    """Pick the most common live client tab; 'none' when empty/idle."""
    if not _client_tabs:
        return "none"
    counts: dict[str, int] = {}
    for tab in _client_tabs.values():
        if tab == "none":
            continue
        counts[tab] = counts.get(tab, 0) + 1
    if not counts:
        return "none"
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def client_count() -> int:
    return len(_client_tabs)


def snapshot() -> dict[str, Any]:
    return {
        "clients": client_count(),
        "dominant_tab": get_dominant_tab(),
        "tabs": dict(_client_tabs),
    }
