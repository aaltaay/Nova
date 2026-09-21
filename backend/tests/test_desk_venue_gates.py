"""ADR 020 -- every Sim-only market gate keys on the Sim venue; Paper shows the live market like Live.

Each gate that hides the live market from the desk's panels on Sim (tape,
depth, quotes, ticker snapshot, chart bars, sensors, the tape WebSocket, the
Sim feed at bootstrap) is exercised on Paper and Live, where it must let the
live market through, and on Sim, where it must still hide it. Also the
``/api/ibkr/status`` overlay per venue.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ibkr import client as _client
from ibkr import safety as _safety
from sim.mode import reset_for_tests, set_venue

LIVE_LIKE = ["paper", "live"]


@pytest.fixture(autouse=True)
def _clean_venue():
    reset_for_tests()
    yield
    reset_for_tests()


# ── tape prints and depth books reach the panels ─────────────────────────────

@pytest.mark.parametrize("target", LIVE_LIKE)
def test_tape_prints_are_shown_off_sim(target: str) -> None:
    from ibkr import tape_events

    set_venue(target)
    assert tape_events._practice_desk() is False
    set_venue("sim")
    assert tape_events._practice_desk() is True


@pytest.mark.parametrize("target", LIVE_LIKE)
def test_live_books_are_broadcast_off_sim(monkeypatch, target: str) -> None:
    from ibkr.depth import handlers, state

    shown: list[dict] = []
    monkeypatch.setattr(state, "push_book", lambda sym, book: shown.append(book))
    set_venue(target)
    handlers._broadcast_live("IMCC", {"bids": [], "asks": []})
    assert len(shown) == 1
    set_venue("sim")
    handlers._broadcast_live("IMCC", {"bids": [], "asks": []})
    assert len(shown) == 1, "Sim still hides the live book"


@pytest.mark.parametrize("target", LIVE_LIKE)
def test_depth_subscribe_takes_the_live_line_off_sim(monkeypatch, target: str) -> None:
    import importlib

    from ibkr.depth import state

    subscribe = importlib.import_module("ibkr.depth.subscribe")
    monkeypatch.setattr(_client, "is_ready", lambda: False)
    monkeypatch.setattr(_client, "unavailable_detail", lambda what: f"{what} unavailable")
    set_venue(target)
    result = asyncio.run(subscribe.subscribe_async("IMCC"))
    assert result["ok"] is False and "unavailable" in result["error"], "went for the real IBKR line"
    assert not state.is_subscribed("IMCC"), "no replay slot on a live-like venue"
    set_venue("sim")
    assert asyncio.run(subscribe.subscribe_async("IMCC"))["ok"] is True
    assert state.is_subscribed("IMCC") and not state.is_live("IMCC")
    state.clear_symbol("IMCC")


# ── quotes, snapshots and candles come from IBKR ─────────────────────────────

def _forbid(name: str):
    def _raise(*args, **kwargs):
        raise AssertionError(f"{name} must not be read on this venue")

    return _raise


@pytest.mark.parametrize("target", LIVE_LIKE)
def test_last_quotes_read_the_live_l1_off_sim(monkeypatch, target: str) -> None:
    from ibkr import ticks
    from sim import market as sim_market

    live = {"IMCC": {"price": 6.2}}
    monkeypatch.setattr(ticks._status, "last_quotes", lambda subs, symbols: live)
    monkeypatch.setattr(sim_market, "last_quotes", _forbid("sim.market.last_quotes"))
    set_venue(target)
    assert ticks.last_quotes(["IMCC"]) is live
    set_venue("sim")
    monkeypatch.setattr(sim_market, "last_quotes", lambda symbols: {"IMCC": {"price": 1.0}})
    assert ticks.last_quotes(["IMCC"]) == {"IMCC": {"price": 1.0}}


@pytest.mark.parametrize("target", LIVE_LIKE)
def test_ticker_snapshot_is_the_ibkr_one_off_sim(monkeypatch, target: str) -> None:
    import ticker_ibkr
    from sim import market as sim_market

    row = {"current_price": 6.2, "previous_close": 5.0, "volume": 1000, "exchange": "NSDQ", "open": 5.5}
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda symbol: row)
    monkeypatch.setattr(sim_market, "ticker_snapshot", _forbid("sim.market.ticker_snapshot"))
    set_venue(target)
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("IMCC")
    assert snap and snap["daily_bar"]["close"] == 6.2
    set_venue("sim")
    monkeypatch.setattr(sim_market, "ticker_snapshot", lambda symbol: {"replayed": symbol})
    assert ticker_ibkr.fetch_ticker_snapshot_ibkr("IMCC") == {"replayed": "IMCC"}


@pytest.mark.parametrize("target", LIVE_LIKE)
def test_chart_bars_skip_the_replay_off_sim(monkeypatch, target: str) -> None:
    import chart_bars
    from sim import chart_replay

    monkeypatch.setattr(chart_replay, "fetch_replay_bars", _forbid("sim.chart_replay.fetch_replay_bars"))
    monkeypatch.setattr(chart_bars, "fetch_alpaca_bars", lambda symbol, tf, limit: {"symbol": symbol, "bars": []})
    set_venue(target)
    assert chart_bars.fetch_chart_bars("IMCC", discovery_provider="alpaca")["source"] == "alpaca"
    set_venue("sim")
    monkeypatch.setattr(chart_replay, "fetch_replay_bars", lambda s, tf, limit: {"source": "replay"})
    assert chart_bars.fetch_chart_bars("IMCC", discovery_provider="alpaca")["source"] == "replay"


@pytest.mark.parametrize("target", LIVE_LIKE)
def test_sensors_label_ibkr_and_default_to_the_liquid_symbol_off_sim(monkeypatch, target: str) -> None:
    from ibkr.depth import state as depth_state
    from sensors import feeds, symbol as sensor_symbol
    from sim import practice

    book = {"bids": [{"price": 9.9, "size": 100}], "asks": [{"price": 10.1, "size": 100}]}
    monkeypatch.setattr(depth_state, "current_book", lambda symbol: book)
    monkeypatch.setattr(practice, "loaded", lambda: practice.Loaded("historical", "IMCC", ("k",)))
    set_venue(target)
    assert feeds.get_book("IMCC") == (book, "ibkr_depth")
    assert sensor_symbol.resolve_symbol(None) == "AAPL", "a loaded replay only steers Sim"
    set_venue("sim")
    assert feeds.get_book("IMCC") == (book, "replay")
    assert sensor_symbol.resolve_symbol(None) == "IMCC"


# ── the tape WebSocket subscribes the live line ──────────────────────────────

class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def accept(self) -> None:
        return None

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("target", LIVE_LIKE)
def test_tape_ws_subscribes_the_live_line_off_sim(monkeypatch, target: str) -> None:
    from ibkr import tape_stream
    from routes.trading_tape_ws import run_ws_tape

    asked: list[str] = []

    async def fake_subscribe(symbol: str) -> dict:
        asked.append(symbol)
        return {"ok": False, "error": "no tape line"}

    monkeypatch.setattr(_client, "is_connected", lambda: True)
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda symbol: False)
    monkeypatch.setattr(tape_stream, "subscribe_async", fake_subscribe)
    monkeypatch.setattr(tape_stream, "ws_viewer_opened", _forbid("viewer opened after a refused line"))
    set_venue(target)
    ws = FakeWebSocket()
    asyncio.run(run_ws_tape(ws, "imcc"))
    assert asked == ["IMCC"] and ws.closed and "no tape line" in ws.sent[-1]


def test_tape_ws_on_sim_never_opens_a_live_line(monkeypatch) -> None:
    from ibkr import tape_stream
    from routes.trading_tape_ws import run_ws_tape

    monkeypatch.setattr(tape_stream, "is_subscribed", lambda symbol: False)
    monkeypatch.setattr(tape_stream, "subscribe_async", _forbid("tape_stream.subscribe_async"))

    def stop_here(symbol: str) -> None:
        raise RuntimeError("stop before streaming")

    monkeypatch.setattr(tape_stream, "ws_viewer_opened", stop_here)
    set_venue("sim")
    asyncio.run(run_ws_tape(FakeWebSocket(), "IMCC"))


# ── bootstrap starts the Sim feed on the Sim venue only ──────────────────────

@pytest.mark.parametrize(("target", "expect_feed"), [("paper", False), ("live", False), ("sim", True)])
def test_bootstrap_starts_the_sim_feed_only_on_sim(monkeypatch, target: str, expect_feed: bool) -> None:
    import app_lifespan
    import startup_reconciliation
    from ibkr import loop_supervisor
    from sim import feed

    started: list[str] = []
    monkeypatch.setattr(app_lifespan, "_local_startup", lambda: None)
    monkeypatch.setattr(app_lifespan, "_mark_nova_api_health", AsyncMock())
    monkeypatch.setattr(loop_supervisor, "set_http_loop", lambda loop: None)
    monkeypatch.setattr(loop_supervisor, "start", lambda: None)
    monkeypatch.setattr(loop_supervisor, "spawn_ib", lambda name, fn: None)
    monkeypatch.setattr(app_lifespan._ibkr_client, "startup", AsyncMock())
    monkeypatch.setattr(app_lifespan, "_wait_ibkr_connected", AsyncMock(return_value=False))
    monkeypatch.setattr(startup_reconciliation, "run_startup_reconciliation", lambda: None)
    monkeypatch.setattr(app_lifespan, "_spawn_runtime_tasks", lambda: [])
    monkeypatch.setattr(feed, "start_sim_feed", lambda: started.append(target))
    set_venue(target)
    asyncio.run(app_lifespan._bootstrap_runtime())
    assert bool(started) is expect_feed


# ── /api/ibkr/status per venue ───────────────────────────────────────────────

def _status_client(monkeypatch) -> TestClient:
    from ibkr import port_diagnostics, session_errors
    from routes.trading import router

    ports = {"preferred_port": 4001, "alternate_port": 4002, "preferred_port_reachable": False,
             "alternate_port_reachable": False, "disconnect_hint": None, "live_port": 4001, "paper_port": 4002}
    monkeypatch.setattr(port_diagnostics, "status_port_fields", lambda connected: ports)
    monkeypatch.setattr(session_errors, "is_delayed_data", lambda: False)
    monkeypatch.setattr(_client, "is_enabled", lambda: False)
    monkeypatch.setattr(_client, "is_ready", lambda: False)
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_status_on_paper_is_novas_practice_account_on_the_real_feed_state(monkeypatch) -> None:
    client = _status_client(monkeypatch)
    set_venue("paper")
    body = client.get("/api/ibkr/status").json()
    assert (body["mode"], body["venue"], body["sim"]) == ("paper", "paper", False)
    assert body["account_id"] == "NOVA-PAPER" and body["account_ids"] == ["NOVA-PAPER"]
    assert body["broker_account_kind"] == "paper"
    assert body["connected"] is False and body["enabled"] is False, "Paper needs the feed; never forced"
    assert body["spend_status"] == "locked_disarmed" and body["trading_allowed"] is False
    assert body["spend_permitted"] is True and body["armed_for_account_kind"] is None
    assert body["trading_allowed_reason"] == _safety.DISARMED_REASON
    armed = client.post("/api/ibkr/arm", json={"armed": True})
    assert armed.status_code == 200 and armed.json()["spend_status"] == "paper_armed"
    body = client.get("/api/ibkr/status").json()
    assert body["spend_status"] == "paper_armed" and body["trading_allowed"] is True and body["armed"] is True
    assert body["connected"] is False


def test_status_on_sim_and_live(monkeypatch) -> None:
    client = _status_client(monkeypatch)
    set_venue("sim")
    _safety.set_armed(True, reason="operator")
    sim = client.get("/api/ibkr/status").json()
    assert (sim["mode"], sim["venue"], sim["sim"], sim["account_id"]) == ("sim", "sim", True, "NOVA-SIM")
    assert sim["connected"] is True and sim["spend_status"] == "sim_armed" and sim["trading_allowed"] is True
    set_venue("live")
    live = client.get("/api/ibkr/status").json()
    assert (live["mode"], live["venue"], live["sim"], live["account_id"]) == ("disconnected", "live", False, None)
    assert live["spend_status"] == "locked" and live["trading_allowed"] is False


def test_status_venue_switch_disarms_and_the_gateway_switch_does_not_move_it(monkeypatch) -> None:
    client = _status_client(monkeypatch)
    set_venue("paper")
    _safety.set_armed(True, reason="operator")
    monkeypatch.setattr(_client, "request_gateway_mode", AsyncMock(return_value={"ok": True, "mode": "paper"}))
    assert client.post("/api/ibkr/gateway-mode", json={"mode": "paper"}).status_code == 200
    assert client.get("/api/ibkr/status").json()["venue"] == "paper"
    assert client.get("/api/ibkr/status").json()["armed"] is True
    from routes.desk import router as desk_router

    client.app.include_router(desk_router)
    assert client.post("/api/desk/venue", json={"venue": "sim"}).json()["venue"] == "sim"
    body = client.get("/api/ibkr/status").json()
    assert body["venue"] == "sim" and body["armed"] is False and body["spend_status"] == "locked_disarmed"
