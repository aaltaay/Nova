"""Opening a stock asks for its history ahead of everything else (operator 2026-11-04).

"When I open a stock, I want to see everything being populated without a question." A stock filled earlier today
used to reopen behind the desk's own refreshes: its panes asked as painted charts, and CRIS's 1-minute chart waited
683 s while IBKR was answering in 0.2 s.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import bars_store
from constants import CHART_DEFAULT_BARS, IBKR_BARS_OPEN_TIMEFRAMES
from ibkr import historical_service
from routes import ticker as ticker_routes


def _open(monkeypatch, symbol: str, panes: list[str], provider: str = "ibkr") -> list[tuple]:
    asked: list[tuple] = []
    monkeypatch.setattr(ticker_routes, "_get_discovery_provider", lambda: provider)
    monkeypatch.setattr(ticker_routes, "_open_timeframes_to_fill", lambda _symbol: panes)
    monkeypatch.setattr(ticker_routes, "ticker_alpaca_required_error", lambda _symbol: {"error": "not needed here"})
    monkeypatch.setattr(ticker_routes, "mark_resub", lambda: None)
    monkeypatch.setattr(ticker_routes._ibkr_ticks, "subscribe", AsyncMock())
    monkeypatch.setattr(ticker_routes._ibkr_ticks, "unsubscribe", AsyncMock())
    monkeypatch.setattr(historical_service, "schedule_fill", lambda *args, **kw: asked.append((args, kw)))
    app = FastAPI()
    app.include_router(ticker_routes.router)
    with TestClient(app).websocket_connect(f"/ws/ticker/{symbol}") as ws:
        assert ws.receive_json()["type"] == "initial"
    return asked


def test_opening_a_stock_asks_for_its_panes_as_an_open_chart(monkeypatch):
    asked = _open(monkeypatch, "cris", ["5Min", "1Min", "10Sec"])
    assert asked == [(("CRIS", tf, CHART_DEFAULT_BARS), {"priority": "open_chart"}) for tf in ("5Min", "1Min", "10Sec")]


def test_no_history_is_asked_of_ibkr_when_it_is_not_the_feed(monkeypatch):
    assert _open(monkeypatch, "CRIS", ["1Min"], provider="alpaca") == []


def test_the_panes_asked_for_are_the_ones_missing_short_or_stale(monkeypatch):
    painted = {"bars": [{"t": 1}], "coverage": {"fetched_ts": 1.0}}
    monkeypatch.setattr(bars_store, "read", lambda _symbol, tf, _limit: painted if tf != "10Sec" else None)
    monkeypatch.setattr(bars_store, "store_series_complete", lambda tf, _count: tf != "5Min")
    monkeypatch.setattr(bars_store, "is_coverage_fresh", lambda _coverage, tf: tf != "1Min")
    assert ticker_routes._open_timeframes_to_fill("CRIS") == [
        tf for tf in IBKR_BARS_OPEN_TIMEFRAMES if tf in ("10Sec", "5Min", "1Min")]
    assert {"10Sec", "5Min", "1Min"} <= set(IBKR_BARS_OPEN_TIMEFRAMES)
