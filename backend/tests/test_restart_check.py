"""What a backend restart would interrupt (ADR 038 amendment): the desk asks before it restarts.

The operator's "Restart backend now" lists these; the nightly sync restarts only when ``safe`` is
true. A reader that fails is ``unknown`` -- never read as "nothing open".
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from diagnostics import restart_check as rc
from stock_mode import store


def _reader(items):
    return lambda: list(items)


def _boom():
    raise RuntimeError("cache unreadable")


def test_nothing_open_and_every_reader_answered_is_safe():
    out = rc.restart_check((("a", _reader([])), ("b", _reader([]))), now=1.0)
    assert out == {"schema_version": 1, "generated_at": 1.0, "safe": True, "open": [], "unknown": []}


def test_anything_open_is_not_safe():
    item = rc._item("recording", "Recording MSGY", symbol="MSGY")
    out = rc.restart_check((("recording", _reader([item])),))
    assert out["safe"] is False
    assert out["open"] == [item]


def test_a_reader_that_fails_is_unknown_never_nothing_open():
    out = rc.restart_check((("ibkr", _boom), ("recording", _reader([]))))
    assert out["safe"] is None
    assert out["unknown"] == [{"kind": "ibkr", "error": "RuntimeError: cache unreadable"}]


def test_something_open_stays_not_safe_when_another_reader_fails():
    item = rc._item("position", "Paper position APUS 100", venue="paper", symbol="APUS")
    out = rc.restart_check((("practice", _reader([item])), ("ibkr", _boom)))
    assert out["safe"] is False
    assert [u["kind"] for u in out["unknown"]] == ["ibkr"]


def test_order_text_reads_like_the_ticket():
    row = {"side": "SELL", "qty": 100, "remaining_qty": 100, "symbol": "APUS", "order_type": "LMT",
           "limit_price": 4.96}
    assert rc.order_text(row) == "SELL 100 APUS LMT 4.96"
    assert rc.order_text({"side": "BUY", "qty": 5, "symbol": "X", "order_type": "STP", "stop_price": 2.5}) \
        == "BUY 5 X STP 2.5"


def test_practice_lists_loaded_ledgers_only(monkeypatch):
    paper = SimpleNamespace(
        ledger=SimpleNamespace(position_rows=lambda: [{"symbol": "APUS", "qty": 100.0}]),
        working_orders=lambda: [{"side": "SELL", "qty": 100, "symbol": "APUS", "order_type": "LMT",
                                 "limit_price": 5.2}],
    )
    monkeypatch.setattr("practice.broker.loaded", lambda venue: paper if venue == "paper" else None)
    items = rc.practice()
    assert [(i["kind"], i["venue"], i["symbol"]) for i in items] == [
        ("position", "paper", "APUS"), ("working_order", "paper", "APUS"),
    ]
    assert "Paper working order SELL 100 APUS LMT 5.2" in items[1]["text"]


def test_ibkr_without_a_ready_session_watches_nothing(monkeypatch):
    monkeypatch.setattr("ibkr.client.get_ib", lambda: None)
    assert rc.ibkr() == []


def test_ibkr_lists_cached_positions_and_open_orders(monkeypatch):
    pos = SimpleNamespace(position=50.0, contract=SimpleNamespace(symbol="MSGY"))
    flat = SimpleNamespace(position=0.0, contract=SimpleNamespace(symbol="FLAT"))
    ib = SimpleNamespace(positions=lambda: [pos, flat], openTrades=lambda: ["t"])
    monkeypatch.setattr("ibkr.client.get_ib", lambda: ib)
    monkeypatch.setattr("ibkr.order_rows.trade_to_order_row", lambda t: {
        "side": "BUY", "qty": 10, "symbol": "SSTI", "order_type": "LMT", "limit_price": 3.1,
    })
    items = rc.ibkr()
    assert [(i["kind"], i["symbol"]) for i in items] == [("position", "MSGY"), ("working_order", "SSTI")]


def test_an_open_bot_trade_is_listed(monkeypatch):
    monkeypatch.setattr("bot.session.raw", lambda: {"trade": {"state": "open", "symbol": "APUS", "venue": "paper"}})
    assert [i["symbol"] for i in rc.bot_trade()] == ["APUS"]
    monkeypatch.setattr("bot.session.raw", lambda: {"trade": {"state": "closed", "symbol": "APUS"}})
    assert rc.bot_trade() == []


def test_stock_modes_in_memory_are_listed():
    store.reset_for_tests()
    try:
        store.set_switch("APUS", {"buy": "nova", "sell": "you", "risk_usd": 50, "set_at": 1.0})
        store.set_switch("QUIET", {"buy": "you", "sell": "you", "risk_usd": None, "set_at": 1.0})
        store.set_approval("MSGY", {"state": "waiting", "setup_id": "x"})
        items = rc.stock_modes()
        assert [i["symbol"] for i in items] == ["APUS", "MSGY"]
        assert "Signal only" in items[0]["text"]
    finally:
        store.reset_for_tests()


def test_running_downloads_are_listed(monkeypatch):
    monkeypatch.setattr("sim.history_download.running_ids", lambda: ["job-1"])
    assert rc.downloads()[0]["kind"] == "download"
    monkeypatch.setattr("sim.history_download.running_ids", lambda: [])
    assert rc.downloads() == []


def test_the_route_answers_the_check(monkeypatch):
    monkeypatch.setattr(rc, "READERS", (("recording", _reader([rc._item("recording", "Recording X", symbol="X")])),))
    from main import app

    body = TestClient(app).get("/api/diagnostics/restart-check").json()
    assert body["schema_version"] == 1
    assert body["safe"] is False
    assert body["open"][0]["symbol"] == "X"


def test_health_names_the_checkout_that_runs_it():
    from main import app

    body = TestClient(app).get("/api/health").json()
    assert body["frozen"] is False
    assert isinstance(body["repo_root"], str) and body["repo_root"]
