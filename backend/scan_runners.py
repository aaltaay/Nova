"""
Scanner runner functions — discovery, focus, after-hours, and movers.

Strangler facade (Phase 8A): orchestration lives in ``scanner_runners.*``;
this module re-exports the public API and symbols tests monkeypatch.
"""
from __future__ import annotations

from alpaca import _alpaca_headers, _get_discovery_provider
from cache import save_afterhours_snapshot, save_gapper_snapshot, save_movers_snapshot
from ibkr import discovery as _ibkr_discovery
from ibkr_bridge import enrich_ibkr_mover, run_ibkr
from runtime_state import get_runtime_state
from scanner import _check_news
from scanner_runners.afterhours import run_afterhours_discovery_scan, run_afterhours_focus_scan
from scanner_runners.discovery import run_discovery_scan, run_focus_scan
from scanner_runners.movers import run_gainers_update
from universe import ensure_avg_volume, enrich_gappers
from websocket import mark_resub

__all__ = [
    "run_discovery_scan",
    "run_focus_scan",
    "run_afterhours_discovery_scan",
    "run_afterhours_focus_scan",
    "run_gainers_update",
    # Re-exported for tests / monkeypatch compatibility
    "get_runtime_state",
    "_alpaca_headers",
    "_get_discovery_provider",
    "_ibkr_discovery",
    "run_ibkr",
    "ensure_avg_volume",
    "_check_news",
    "enrich_gappers",
    "mark_resub",
    "save_gapper_snapshot",
    "save_afterhours_snapshot",
    "save_movers_snapshot",
    "enrich_ibkr_mover",
]
