"""Journal-on-close from ledger flatten -- local facts only, no live IBKR."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.store as store
import execution.telemetry as telemetry
import execution.telemetry_persist as telemetry_persist
import journal.db as journal_db
import journal.round_trip as round_trip
from execution.store_facts import record_broker_facts
from journal.store import get_closed_trades


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
        raise AssertionError("journal flatten must not call IB")

    monkeypatch.setattr("ibkr.client.get_ib", boom)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)


def _filled_place(
    *,
    key: str,
    symbol: str,
    side: str,
    qty: float,
    price: float | None,
    source: str,
    received_ns: int,
    order_id: int,
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
    if price is not None:
        record_broker_facts(exec_id, filled_qty=qty, avg_fill_price=price)
    else:
        record_broker_facts(exec_id, filled_qty=qty)
    return exec_id


def test_flatten_fill_writes_journal_from_ledger_without_ib(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

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
    )

    trade = on_flatten_fill_recorded(flatten_id, since_ts=0)

    assert trade is not None
    assert trade["symbol"] == "IVF"
    assert trade["side"] == "long"
    assert trade["qty"] == 10
    assert trade["entry_price"] == pytest.approx(5.0)
    assert trade["exit_price"] == pytest.approx(6.5)
    assert trade["pnl"] == pytest.approx(15.0)
    assert trade["is_mock"] == 0
    assert trade["close_key"] == f"IVF|{buy_id}|{flatten_id}"
    assert "gross of commissions" in (trade["notes"] or "")
    assert get_closed_trades() == [trade]
    assert round_trip.open_cycles() == {}


def test_flatten_without_fill_price_does_not_invent_pnl(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

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
        price=None,
        source="flatten",
        received_ns=2,
        order_id=202,
    )

    assert on_flatten_fill_recorded(flatten_id, since_ts=0) is None
    assert get_closed_trades() == []


def test_flatten_alone_does_not_open_a_cycle(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    _forbid_ib(monkeypatch)
    flatten_id = _filled_place(
        key="flatten:sell:ORPH:1",
        symbol="ORPH",
        side="SELL",
        qty=2.0,
        price=9.0,
        source="flatten",
        received_ns=1,
        order_id=301,
    )

    assert on_flatten_fill_recorded(flatten_id, since_ts=0) is None
    assert get_closed_trades() == []
    assert "ORPH" not in round_trip.open_cycles()


def test_manual_close_is_not_a_flatten_trigger(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    _forbid_ib(monkeypatch)
    _filled_place(
        key="open-buy",
        symbol="AAPL",
        side="BUY",
        qty=1.0,
        price=3.0,
        source="manual",
        received_ns=1,
        order_id=401,
    )
    sell_id = _filled_place(
        key="manual-sell",
        symbol="AAPL",
        side="SELL",
        qty=1.0,
        price=4.0,
        source="manual",
        received_ns=2,
        order_id=402,
    )

    assert on_flatten_fill_recorded(sell_id, since_ts=0) is None
    assert get_closed_trades() == []


def test_flatten_hook_is_idempotent(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    _forbid_ib(monkeypatch)
    _filled_place(
        key="open-buy",
        symbol="NVDA",
        side="BUY",
        qty=1.0,
        price=8.0,
        source="manual",
        received_ns=1,
        order_id=501,
    )
    flatten_id = _filled_place(
        key="flatten:sell:NVDA:1",
        symbol="NVDA",
        side="SELL",
        qty=1.0,
        price=9.0,
        source="flatten",
        received_ns=2,
        order_id=502,
    )

    first = on_flatten_fill_recorded(flatten_id, since_ts=0)
    second = on_flatten_fill_recorded(flatten_id, since_ts=0)
    assert first is not None
    assert second is None
    assert len(get_closed_trades()) == 1


def test_short_cover_flatten_uses_ledger_prices(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    _forbid_ib(monkeypatch)
    _filled_place(
        key="open-short",
        symbol="TSLA",
        side="SELL",
        qty=5.0,
        price=20.0,
        source="manual",
        received_ns=1,
        order_id=601,
    )
    flatten_id = _filled_place(
        key="flatten:buy:TSLA:1",
        symbol="TSLA",
        side="BUY",
        qty=5.0,
        price=17.0,
        source="flatten",
        received_ns=2,
        order_id=602,
    )

    trade = on_flatten_fill_recorded(flatten_id, since_ts=0)
    assert trade is not None
    assert trade["side"] == "short"
    assert trade["entry_price"] == pytest.approx(20.0)
    assert trade["exit_price"] == pytest.approx(17.0)
    assert trade["pnl"] == pytest.approx(15.0)


def test_submit_facts_on_flatten_journals_without_ib_watch(monkeypatch):
    from journal.flatten_close import is_flatten_ledger_row

    _forbid_ib(monkeypatch)
    buy_id = _filled_place(
        key="open-buy",
        symbol="AMD",
        side="BUY",
        qty=2.0,
        price=4.0,
        source="manual",
        received_ns=1,
        order_id=701,
    )
    flatten_id, _ = store.reserve(
        idempotency_key="flatten:sell:AMD:facts",
        operation="place",
        source="flatten",
        symbol="AMD",
        received_ns=2,
        payload={"side": "SELL", "qty": 2.0},
    )
    store.update_stages(flatten_id, status="sent", order_id=702)
    assert is_flatten_ledger_row(store.get_by_id(flatten_id) or {})

    telemetry_persist.submit_facts(
        702,
        flatten_id,
        perm_id=None,
        filled_qty=2.0,
        avg_fill_price=5.0,
    )

    trades = get_closed_trades()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "AMD"
    assert trades[0]["pnl"] == pytest.approx(2.0)
    assert trades[0]["close_key"] == f"AMD|{buy_id}|{flatten_id}"
