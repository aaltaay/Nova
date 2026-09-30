"""The Cryptos page's refreshers and routes (ADR 040): what runs when, how failures are stated, and the wire."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crypto import candles, coinbase, coingecko, feeds, ibkr_reads, news, refresh
from crypto.state import store
from crypto.web import SourceError

NOW = 1_790_000_000.0


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    refresh.reset_for_tests()
    ran: list[str] = []

    def stub(name, value):
        def fetch(*args, **kwargs):
            ran.append(name)
            return value
        return fetch

    monkeypatch.setattr(coingecko, "fetch_markets", stub("markets", {"bitcoin": {"price": 1.0}}))
    monkeypatch.setattr(coingecko, "fetch_global", stub("global", {"total_cap_usd": 1.0}))
    monkeypatch.setattr(coingecko, "fetch_volume_history", stub("volume", [1.0]))
    monkeypatch.setattr(feeds, "fetch_perps", stub("perps", {}))
    monkeypatch.setattr(feeds, "fetch_fear_greed", stub("fear_greed", {"value": 50}))
    monkeypatch.setattr(feeds, "fetch_stablecoins", stub("stablecoins", {"supply_usd": 1.0}))
    monkeypatch.setattr(feeds, "fetch_option_expiries", stub("expiries", []))
    monkeypatch.setattr(news, "fetch_news", stub("news", {}))
    monkeypatch.setattr(coinbase, "fetch_series", stub("series", [{"t": 0, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]))
    monkeypatch.setattr(coinbase, "fetch_history", stub("history", []))
    monkeypatch.setattr(refresh, "_start", lambda: None)
    yield ran
    refresh.reset_for_tests()


def drain(lane: str, now: float, limit: int = 60) -> int:
    n = 0
    while n < limit and refresh.run_once(lane, now):
        n += 1
    return n


def test_nothing_runs_until_the_page_asks_and_a_chart_it_asks_for_goes_first(fresh):
    refresh.want(NOW)
    refresh.want_candles("SOL", "1h", NOW)
    assert refresh.run_once("web", NOW)
    assert store().answered_at("candles:SOL:1h") is not None
    assert refresh.run_once("web", NOW) and store().answered_at("candles:SOL:15m") is not None
    drain("web", NOW)
    for key in ("markets", "global", "perps", "fear_greed", "news", "stablecoins", "expiries", "hourly:BTC",
                "candles:ETH:15m"):
        assert store().answered_at(key) is not None, key
    assert fresh.count("volume") == 1   # the histories are spaced: one per gap
    assert not refresh.run_once("web", NOW + 1)
    assert refresh.run_once("web", NOW + 16) and fresh.count("volume") == 2


def test_a_failure_is_stated_and_retried_later(fresh, monkeypatch):
    def boom():
        raise SourceError("HTTP 500")

    monkeypatch.setattr(feeds, "fetch_perps", boom)
    refresh.want(NOW)
    drain("web", NOW)
    hl = next(s for s in store().statuses(NOW) if s["id"] == "hyperliquid")
    assert hl == {"id": "hyperliquid", "label": "Hyperliquid", "ok": False, "at": None, "error": "perps: HTTP 500"}
    assert not store().due("perps", "hyperliquid", NOW + 30, 60)
    assert store().due("perps", "hyperliquid", NOW + 61, 60)


def test_a_rate_limit_holds_every_read_of_that_source(fresh, monkeypatch):
    def limited():
        raise SourceError("HTTP 429 (rate limited)")

    monkeypatch.setattr(coingecko, "fetch_markets", limited)
    refresh.want(NOW)
    drain("web", NOW)
    assert store().answered_at("global") is None     # held behind the 429, not asked into it
    assert "global" not in fresh


def test_an_unexpected_error_is_recorded_not_raised(fresh, monkeypatch):
    def bad():
        raise KeyError("price")

    monkeypatch.setattr(feeds, "fetch_fear_greed", bad)
    refresh.want(NOW)
    drain("web", NOW)
    fg = next(s for s in store().statuses(NOW) if s["id"] == "fear_greed")
    assert fg["ok"] is False and fg["error"].startswith("fear_greed: KeyError")


def test_ibkr_reads_wait_for_a_connected_gateway(monkeypatch):
    monkeypatch.setattr(ibkr_reads, "ready", lambda: False)
    refresh.want(NOW)
    assert refresh.run_once("ibkr", NOW) is False
    ibkr = next(s for s in store().statuses(NOW) if s["id"] == "ibkr")
    assert ibkr["ok"] is False and ibkr["error"] == "IBKR is not connected"


def test_daily_closes_are_asked_again_until_the_session_lands_and_a_shed_is_not_a_failure(monkeypatch):
    asked: list[str] = []

    class HistoricalShed(Exception):
        pass

    def closes(symbol):
        asked.append(symbol)
        if symbol == "ETHA":
            raise HistoricalShed("open chart has priority")
        return {"2026-09-01": 10.0}      # never the reference session

    monkeypatch.setattr(ibkr_reads, "ready", lambda: True)
    monkeypatch.setattr(ibkr_reads, "quotes", lambda symbols: {s: None for s in symbols})
    monkeypatch.setattr(ibkr_reads, "rth_closes", closes)
    monkeypatch.setattr(ibkr_reads, "listing", lambda symbol: {"listed": False, "venue": None})
    refresh.want(NOW)
    assert refresh.run_once("ibkr", NOW) and store().answered_at("bridge_quotes") is not None
    assert refresh.run_once("ibkr", NOW) and asked == ["IBIT"]
    assert refresh.run_once("ibkr", NOW + 6) and asked == ["IBIT", "ETHA"]
    assert store().result("closes:ETHA") is None                  # shed: deferred, not failed
    assert not store().due("closes:IBIT", "ibkr", NOW + 100, 0.0)  # not the session yet: asked again later
    assert store().due("closes:IBIT", "ibkr", NOW + 601, 0.0)


def test_the_switch_turns_the_refreshers_off(monkeypatch):
    monkeypatch.setenv("NOVA_CRYPTO", "0")
    assert refresh.enabled() is False
    monkeypatch.setenv("NOVA_CRYPTO", "1")
    assert refresh.enabled() is True


def test_the_candle_view_answers_loading_then_the_levels():
    s = store()
    view = candles.view(s, "BTC", "15m", NOW)
    assert view["loading"] is True and view["candles"] == [] and view["last"] is None
    rows = [{"t": int(NOW) - 86400 + i * 900, "o": 100.0 + i, "h": 101.0 + i, "l": 99.0 + i, "c": 100.5 + i, "v": 1.0}
            for i in range(96)]
    s.put("candles:BTC:15m", "coinbase", rows, NOW)
    view = candles.view(s, "BTC", "15m", NOW)
    assert view["loading"] is False and len(view["candles"]) == 96
    assert view["last"] == 195.5 and view["levels"]["high_24h"] == 196.0 and view["levels"]["low_24h"] == 99.0
    assert view["change_24h_pct"] == pytest.approx((195.5 / 100.0 - 1) * 100)
    assert view["product"] == "BTC-USD" and view["source"] == "coinbase"
    s.fail("candles:ETH:1d", "coinbase", "HTTP 404", NOW)
    failed = candles.view(s, "ETH", "1d", NOW)
    assert failed["loading"] is False and failed["error"] == "HTTP 404" and failed["sessions"] == []


def test_routes_answer_the_board_and_refuse_an_unknown_chart(monkeypatch):
    from main import app

    client = TestClient(app)
    body = client.get("/api/crypto/board").json()
    assert body["schema_version"] == 1 and body["enabled"] is False   # the suite pins NOVA_CRYPTO=0
    assert len(body["coins"]) == 13 and body["coins"][0]["symbol"] == "BTC"
    bad = client.get("/api/crypto/candles", params={"symbol": "BNB"})
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "CRYPTO_UNKNOWN_SYMBOL"
    bad_tf = client.get("/api/crypto/candles", params={"symbol": "BTC", "tf": "3m"})
    assert bad_tf.status_code == 400 and bad_tf.json()["detail"]["reason"] == "CRYPTO_UNKNOWN_TF"
    monkeypatch.setenv("NOVA_CRYPTO", "1")
    ok = client.get("/api/crypto/candles", params={"symbol": "eth", "tf": "1h"}).json()
    assert ok["symbol"] == "ETH" and ok["loading"] is True
    assert ("ETH", "1h") in store().wanted_candles(ok["levels"]["day_open_at"] + 1)
