"""Round-trip builder: ledger fills -> journal trades when a symbol flats."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.store as store
import execution.telemetry as telemetry
import journal.db as journal_db
import journal.round_trip as round_trip
from journal.round_trip import FillEvent
from journal.store import get_closed_trades, record_trade


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


def _fill(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    execution_id: str,
    *,
    ts: float = 1_700_000_000.0,
    operation: str = "place",
    source: str = "manual",
    parent_order_id: int | None = None,
) -> FillEvent:
    return FillEvent(
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        ts=ts,
        execution_id=execution_id,
        operation=operation,
        source=source,
        parent_order_id=parent_order_id,
    )


def test_partial_adds_weight_entry_and_write_on_flat():
    assert round_trip.apply_fill(_fill("IVF", "BUY", 10, 5.0, "open-a")) is None
    assert round_trip.apply_fill(_fill("IVF", "BUY", 5, 6.0, "open-b")) is None
    trade = round_trip.apply_fill(_fill("IVF", "SELL", 15, 7.0, "close-a"))
    assert trade is not None
    assert trade["side"] == "long"
    assert trade["qty"] == 15
    assert trade["entry_price"] == pytest.approx(80.0 / 15.0)
    assert trade["exit_price"] == pytest.approx(7.0)
    assert trade["pnl"] == pytest.approx(25.0)
    assert trade["is_mock"] == 0
    assert "gross of commissions" in (trade["notes"] or "")
    assert trade["close_key"] == "IVF|open-a|close-a"
    assert get_closed_trades() == [trade]
    assert round_trip.open_cycles() == {}


def test_scale_out_waits_for_flat():
    assert round_trip.apply_fill(_fill("MSFT", "BUY", 10, 5.0, "e1")) is None
    assert round_trip.apply_fill(_fill("MSFT", "SELL", 4, 6.0, "e2")) is None
    assert "MSFT" in round_trip.open_cycles()
    trade = round_trip.apply_fill(_fill("MSFT", "SELL", 6, 7.0, "e3"))
    assert trade is not None
    assert trade["qty"] == 10
    assert trade["entry_price"] == pytest.approx(5.0)
    assert trade["exit_price"] == pytest.approx(6.6)
    assert trade["pnl"] == pytest.approx(16.0)


def test_short_round_trip():
    assert round_trip.apply_fill(_fill("AAPL", "SELL", 10, 5.0, "s1")) is None
    trade = round_trip.apply_fill(_fill("AAPL", "BUY", 10, 4.0, "s2"))
    assert trade is not None
    assert trade["side"] == "short"
    assert trade["pnl"] == pytest.approx(10.0)
    assert trade["entry_price"] == pytest.approx(5.0)
    assert trade["exit_price"] == pytest.approx(4.0)


def test_flip_through_flat_closes_then_opens_opposite():
    round_trip.apply_fill(_fill("NVDA", "BUY", 10, 5.0, "f1"))
    trade = round_trip.apply_fill(_fill("NVDA", "SELL", 15, 6.0, "f2"))
    assert trade is not None
    assert trade["qty"] == 10
    assert trade["pnl"] == pytest.approx(10.0)
    open_cycle = round_trip.open_cycles()["NVDA"]
    assert open_cycle.net_qty == pytest.approx(-5.0)
    assert open_cycle.open_execution_id == "f2"


def test_skips_benchmark_and_duplicate_same_side():
    assert round_trip.apply_fill(
        _fill("BENCH", "BUY", 1, 1.0, "b1", source="benchmark")
    ) is None
    assert round_trip.open_cycles() == {}
    round_trip.apply_fill(_fill("IVF", "BUY", 1, 2.0, "d1"))
    assert round_trip.apply_fill(_fill("IVF", "BUY", 1, 2.0, "d1")) is None
    assert round_trip.open_cycles()["IVF"].net_qty == pytest.approx(1.0)


def test_restart_rebuild_restores_open_and_does_not_rewrite():
    buy_id, _ = store.reserve(
        idempotency_key="rt-buy",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=1,
        payload={"side": "BUY", "qty": 1},
    )
    store.update_stages(buy_id, status="filled", order_id=19085)
    from execution.store_facts import record_broker_facts

    record_broker_facts(buy_id, filled_qty=1.0, avg_fill_price=3.5)

    written = round_trip.rebuild_from_ledger(since_ts=0)
    assert written == 0
    assert round_trip.open_cycles()["IVF"].net_qty == pytest.approx(1.0)

    sell_id, _ = store.reserve(
        idempotency_key="rt-sell",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=2,
        payload={"side": "SELL", "qty": 1},
    )
    store.update_stages(sell_id, status="filled", order_id=19112)
    record_broker_facts(sell_id, filled_qty=1.0, avg_fill_price=4.25)

    written = round_trip.rebuild_from_ledger(since_ts=0)
    assert written == 1
    trades = get_closed_trades()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "IVF"
    assert trades[0]["pnl"] == pytest.approx(0.75)
    assert round_trip.open_cycles() == {}

    written_again = round_trip.rebuild_from_ledger(since_ts=0)
    assert written_again == 0
    assert len(get_closed_trades()) == 1


def test_bracket_close_key_double_write_is_noop():
    trade = round_trip.apply_fill(
        _fill("AAPL", "BUY", 100, 5.0, "br-open", operation="bracket", parent_order_id=10)
    )
    assert trade is None
    closed = round_trip.apply_fill(
        _fill(
            "AAPL",
            "SELL",
            100,
            5.2,
            "br-close",
            operation="bracket",
            parent_order_id=10,
        )
    )
    assert closed is not None
    assert closed["close_key"] == "AAPL|bracket|10"
    dup = record_trade(
        symbol="AAPL",
        setup="gap_and_go",
        side="long",
        qty=100,
        entry_price=5.0,
        stop_price=4.9,
        target_price=5.2,
        exit_price=5.2,
        pnl=20.0,
        adherent=True,
        close_key="AAPL|bracket|10",
    )
    assert dup == 0
    assert len(get_closed_trades()) == 1


def test_note_filled_place_round_trip_journals():
    buy_id, _ = store.reserve(
        idempotency_key="hook-buy",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=1,
        payload={"side": "BUY", "qty": 1},
    )
    store.update_stages(buy_id, order_id=19085, status="sent")
    buy = telemetry.watch_order(19085, buy_id, side="BUY")
    buy.note_status(
        "Filled", filled=1.0, remaining=0.0, average_fill_price=3.5,
    )
    buy.note_execution(
        avg_price=3.5, price=3.5, shares=1.0, cumulative_shares=1.0,
    )
    buy.note_filled()
    assert "IVF" in round_trip.open_cycles()

    sell_id, _ = store.reserve(
        idempotency_key="hook-sell",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=2,
        payload={"side": "SELL", "qty": 1},
    )
    store.update_stages(sell_id, order_id=19112, status="sent")
    sell = telemetry.watch_order(19112, sell_id, side="SELL")
    sell.note_status(
        "Filled", filled=1.0, remaining=0.0, average_fill_price=4.25,
    )
    sell.note_execution(
        avg_price=4.25, price=4.25, shares=1.0, cumulative_shares=1.0,
    )
    sell.note_filled()
    trades = get_closed_trades()
    assert len(trades) == 1
    assert trades[0]["pnl"] == pytest.approx(0.75)
    assert trades[0]["close_key"] == f"IVF|{buy_id}|{sell_id}"
    assert round_trip.open_cycles() == {}
