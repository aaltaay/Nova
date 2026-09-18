"""D-046 slice 2: journal / Reports net P/L uses CommissionReport only."""
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
from journal.net_pnl import (
    GROSS_NOTE,
    apply_reported_commission,
    gross_pnl,
    net_from_gross,
    reported_commission,
    sum_reported_commissions,
)
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


def test_reported_commission_never_invents_from_avg_cost():
    assert reported_commission(None) is None
    assert reported_commission("") is None
    assert reported_commission("x") is None
    assert reported_commission(1.25) == pytest.approx(1.25)
    assert reported_commission(0.0) == pytest.approx(0.0)
    assert sum_reported_commissions([None, None]) is None
    assert sum_reported_commissions([1.0, None, 0.5]) == pytest.approx(1.5)
    assert net_from_gross(15.0, None) == pytest.approx(15.0)
    assert net_from_gross(15.0, 2.25) == pytest.approx(12.75)
    assert net_from_gross(15.0, -2.0) == pytest.approx(13.0)
    assert gross_pnl("long", 10, 5.0, 6.5) == pytest.approx(15.0)
    # avg_cost 5.10 vs fill 5.00 is not a $0.10 fee
    invented = 5.10 - 5.00
    assert reported_commission(None) is None
    assert net_from_gross(15.0, None) != pytest.approx(15.0 - invented)


def test_flatten_with_commission_reports_writes_net_pnl(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    monkeypatch.setattr("ibkr.client.get_ib", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no IB")))
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)

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
    assert trade["pnl"] == pytest.approx(12.75)
    assert trade["commission"] == pytest.approx(2.25)
    assert buy_id in (trade["fill_ids"] or "")
    assert flatten_id in (trade["fill_ids"] or "")
    assert "net of CommissionReport" in (trade["notes"] or "")
    assert GROSS_NOTE not in (trade["notes"] or "")


def test_flatten_without_commission_report_stays_gross(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)

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

    trade = on_flatten_fill_recorded(flatten_id, since_ts=0)
    assert trade is not None
    assert trade["pnl"] == pytest.approx(4.0)
    assert trade.get("commission") is None
    assert GROSS_NOTE in (trade["notes"] or "")


def test_late_commission_report_updates_existing_journal_row(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)

    buy_id = _filled_place(
        key="open-buy",
        symbol="AMD",
        side="BUY",
        qty=2.0,
        price=4.0,
        source="manual",
        received_ns=1,
        order_id=301,
    )
    flatten_id = _filled_place(
        key="flatten:sell:AMD:1",
        symbol="AMD",
        side="SELL",
        qty=2.0,
        price=5.0,
        source="flatten",
        received_ns=2,
        order_id=302,
    )
    first = on_flatten_fill_recorded(flatten_id, since_ts=0)
    assert first is not None
    assert first["pnl"] == pytest.approx(2.0)
    assert GROSS_NOTE in (first["notes"] or "")

    record_broker_facts(buy_id, commission=0.40)
    record_broker_facts(flatten_id, commission=0.60)
    updated = apply_reported_commission(flatten_id)
    assert updated is not None
    assert updated["pnl"] == pytest.approx(1.0)
    assert updated["commission"] == pytest.approx(1.0)
    assert "net of CommissionReport" in (updated["notes"] or "")
    assert get_closed_trades()[0]["pnl"] == pytest.approx(1.0)


def test_submit_facts_commission_patches_journal_without_ib(monkeypatch):
    from journal.flatten_close import on_flatten_fill_recorded

    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)

    _filled_place(
        key="open-buy",
        symbol="NVDA",
        side="BUY",
        qty=1.0,
        price=8.0,
        source="manual",
        received_ns=1,
        order_id=401,
    )
    flatten_id = _filled_place(
        key="flatten:sell:NVDA:1",
        symbol="NVDA",
        side="SELL",
        qty=1.0,
        price=9.0,
        source="flatten",
        received_ns=2,
        order_id=402,
    )
    assert on_flatten_fill_recorded(flatten_id, since_ts=0)["pnl"] == pytest.approx(1.0)

    telemetry_persist.submit_facts(
        402,
        flatten_id,
        perm_id=None,
        filled_qty=1.0,
        avg_fill_price=9.0,
        commission=0.35,
    )
    trade = get_closed_trades()[0]
    assert trade["pnl"] == pytest.approx(0.65)
    assert trade["commission"] == pytest.approx(0.35)


def test_apply_without_report_does_not_invent_zero_fee():
    assert apply_reported_commission("missing-id") is None
    exec_id, _ = store.reserve(
        idempotency_key="no-comm",
        operation="place",
        source="manual",
        symbol="ZTG",
        received_ns=1,
        payload={"side": "BUY", "qty": 1},
    )
    record_broker_facts(exec_id, filled_qty=1.0, avg_fill_price=2.0)
    assert store.get_by_id(exec_id)["commission"] is None
    assert apply_reported_commission(exec_id) is None


def test_migration_adds_commission_and_fill_ids():
    conn = journal_db.get_connection()
    conn.executescript(
        """
        DROP TABLE IF EXISTS trades;
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_ts REAL NOT NULL,
            closed_ts REAL,
            symbol TEXT NOT NULL,
            setup TEXT,
            side TEXT NOT NULL,
            qty INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            stop_price REAL,
            target_price REAL,
            pnl REAL,
            adherent INTEGER,
            notes TEXT,
            is_mock INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]',
            close_key TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO trades (opened_ts, symbol, side, qty, entry_price, pnl) "
        "VALUES (1.0, 'OLD', 'long', 1, 5.0, 1.0)"
    )
    conn.commit()
    conn.close()

    journal_db.init_db()
    from journal.store import get_closed_trades as closed

    rows = closed(include_mock=True)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "OLD"
    assert rows[0].get("commission") is None
    assert rows[0].get("fill_ids") in (None, "")
