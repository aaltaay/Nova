"""Activity trail -- journal + ledger join, no invented P/L or IB calls."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.store as store
import execution.telemetry as telemetry
import journal.db as journal_db
import journal.round_trip as round_trip
from execution.store_facts import record_broker_facts
from journal.flatten_close import on_flatten_fill_recorded
from journal.store import get_closed_trades, record_trade
from journal.trail import recent_trail


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)
    journal_db.init_db()
    store.init_db()
    round_trip.reset_for_tests()
    telemetry.reset_for_tests()
    yield
    round_trip.reset_for_tests()
    telemetry.reset_for_tests()


def _forbid_ib(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("activity trail must not call IB")

    monkeypatch.setattr("ibkr.client.get_ib", boom)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)


def _filled_place(
    *,
    key: str,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    source: str,
    received_ns: int,
    order_id: int,
    commission: float | None = None,
) -> str:
    exec_id, _ = store.reserve(
        idempotency_key=key,
        operation="place",
        source=source,
        symbol=symbol,
        received_ns=received_ns,
        payload={"side": side, "qty": qty},
    )
    store.update_stages(exec_id, status="filled", order_id=order_id)
    record_broker_facts(
        exec_id,
        filled_qty=qty,
        avg_fill_price=price,
        commission=commission,
    )
    return exec_id


def test_flatten_cycle_is_place_fill_flatten_commission_close(monkeypatch):
    _forbid_ib(monkeypatch)
    buy_id = _filled_place(
        key="open-buy",
        symbol="IVF",
        side="BUY",
        qty=10.0,
        price=5.0,
        source="manual",
        received_ns=1,
        order_id=101,
        commission=1.0,
    )
    flatten_id = _filled_place(
        key="flatten:sell:IVF:1",
        symbol="IVF",
        side="SELL",
        qty=10.0,
        price=6.5,
        source="flatten",
        received_ns=2,
        order_id=102,
        commission=1.25,
    )
    trade = on_flatten_fill_recorded(flatten_id, since_ts=0)
    assert trade is not None

    payload = recent_trail(limit=20)
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["kind"] == "closed"
    assert item["symbol"] == "IVF"
    assert item["side"] == "long"
    assert item["qty"] == pytest.approx(10.0)
    assert item["pnl"] == pytest.approx(12.75)
    assert item["commission"] == pytest.approx(2.25)
    assert item["pnl_basis"] == "net"
    assert item["fill_ids"] == [buy_id, flatten_id]
    assert [event["kind"] for event in item["events"]] == [
        "place",
        "fill",
        "commission",
        "flatten",
        "fill",
        "commission",
        "close",
    ]
    close = item["events"][-1]
    assert close["pnl"] == pytest.approx(12.75)
    assert close["source"] == "journal"


def test_missing_commission_stays_gross_and_omits_fee_event(monkeypatch):
    _forbid_ib(monkeypatch)
    _filled_place(
        key="open-buy",
        symbol="MSFT",
        side="BUY",
        qty=4.0,
        price=10.0,
        source="manual",
        received_ns=1,
        order_id=201,
    )
    flatten_id = _filled_place(
        key="flatten:sell:MSFT:1",
        symbol="MSFT",
        side="SELL",
        qty=4.0,
        price=11.0,
        source="flatten",
        received_ns=2,
        order_id=202,
    )
    on_flatten_fill_recorded(flatten_id, since_ts=0)

    item = recent_trail()["items"][0]
    assert item["commission"] is None
    assert item["pnl_basis"] == "gross"
    assert item["pnl"] == pytest.approx(4.0)
    assert "commission" not in [event["kind"] for event in item["events"]]


def test_imported_trade_is_close_only_and_keeps_stored_pnl(monkeypatch):
    _forbid_ib(monkeypatch)
    record_trade(
        symbol="IMP",
        setup=None,
        side="long",
        qty=100,
        entry_price=1.0,
        stop_price=None,
        target_price=None,
        exit_price=1.48,
        pnl=48.0,
        adherent=None,
        opened_ts=1_741_996_800.0,
        closed_ts=1_741_996_800.0,
        notes="import",
        close_key="import:IMP:1741996800:48",
        commission=2.0,
    )
    item = recent_trail()["items"][0]
    assert item["symbol"] == "IMP"
    assert item["pnl"] == pytest.approx(48.0)
    assert item["commission"] == pytest.approx(2.0)
    assert item["pnl_basis"] is None
    assert [event["kind"] for event in item["events"]] == ["close"]
    prices = (1.48 - 1.0) * 100
    assert item["pnl"] != pytest.approx(prices - 2.0)


def test_open_place_is_session_activity_not_a_closed_cycle(monkeypatch):
    _forbid_ib(monkeypatch)
    _filled_place(
        key="open-only",
        symbol="AAPL",
        side="BUY",
        qty=1.0,
        price=190.0,
        source="manual",
        received_ns=3,
        order_id=301,
    )
    payload = recent_trail()
    assert get_closed_trades() == []
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["kind"] == "open"
    assert item["symbol"] == "AAPL"
    assert item["pnl"] is None
    assert item["closed_ts"] is None
    assert [event["kind"] for event in item["events"]] == ["place", "fill"]


def test_symbol_filter_and_limit(monkeypatch):
    _forbid_ib(monkeypatch)
    _filled_place(
        key="aapl-open",
        symbol="AAPL",
        side="BUY",
        qty=1.0,
        price=10.0,
        source="manual",
        received_ns=1,
        order_id=401,
    )
    _filled_place(
        key="ivf-open",
        symbol="IVF",
        side="BUY",
        qty=1.0,
        price=5.0,
        source="manual",
        received_ns=2,
        order_id=402,
    )
    flatten = _filled_place(
        key="flatten:sell:IVF:1",
        symbol="IVF",
        side="SELL",
        qty=1.0,
        price=6.0,
        source="flatten",
        received_ns=3,
        order_id=403,
    )
    on_flatten_fill_recorded(flatten, since_ts=0)

    ivf = recent_trail(symbol="ivf")
    assert [item["symbol"] for item in ivf["items"]] == ["IVF"]
    assert recent_trail(limit=1)["count"] == 1


def test_trail_route_returns_join(monkeypatch):
    _forbid_ib(monkeypatch)
    _filled_place(
        key="open-buy",
        symbol="IVF",
        side="BUY",
        qty=1.0,
        price=5.0,
        source="manual",
        received_ns=1,
        order_id=501,
        commission=0.5,
    )
    flatten_id = _filled_place(
        key="flatten:sell:IVF:1",
        symbol="IVF",
        side="SELL",
        qty=1.0,
        price=6.0,
        source="flatten",
        received_ns=2,
        order_id=502,
        commission=0.5,
    )
    on_flatten_fill_recorded(flatten_id, since_ts=0)

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    res = client.get("/api/journal/trail?symbol=IVF")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "IVF"
    assert "place" in [event["kind"] for event in body["items"][0]["events"]]
    assert "close" in [event["kind"] for event in body["items"][0]["events"]]
