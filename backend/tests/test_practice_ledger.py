"""Event-sourced practice ledger: derive, unwind, buying power, rollover, contract."""
from __future__ import annotations

from datetime import datetime

import pytest

from practice.clock import ET, day_start_ts
from practice.fees import for_fill
from practice.ledger import EVENT_FILLED, Ledger

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=ET).timestamp()

CONTRACT = {
    "venue", "account_id", "starting_cash", "cash", "buying_power", "net_liquidation",
    "gross_position_value", "realized_pnl", "unrealized_pnl", "day_pnl", "realized_today", "day_started_et",
    "commissions_today", "positions", "working", "fills_today", "schema_version", "updated_at",
}


def row(oid, symbol="IMCC", side="BUY", qty=10, typ="MKT", limit=None, stop=None, ts=T0,
        source="manual", bot_id=None) -> dict:
    return {
        "order_id": oid, "symbol": symbol, "side": side, "qty": float(qty), "filled_qty": 0.0,
        "remaining_qty": float(qty), "order_type": typ, "limit_price": limit, "stop_price": stop,
        "status": "Submitted", "placed_ts": ts, "source": "nova", "order_source": source,
        "bot_id": bot_id,
    }


def test_events_derive_cash_positions_and_realized_net_of_fees() -> None:
    ledger = Ledger(100_000, created_ts=T0)
    ledger.place(row(1), ts=T0, source="manual")
    ledger.fill(1, ts=T0 + 1, price=10.0, basis="quote")
    buy_fees = for_fill("BUY", 10, 10.0).total
    assert ledger.cash == pytest.approx(100_000 - 100 - buy_fees)
    assert (ledger.held_qty("IMCC"), ledger.avg_cost("IMCC")) == (10, 10.0)
    ledger.place(row(2, side="SELL"), ts=T0 + 2, source="bot", bot_id="alpha")
    ledger.fill(2, ts=T0 + 3, price=11.0, basis="print_cross")
    sell_fees = for_fill("SELL", 10, 11.0).total
    assert ledger.realized == pytest.approx(10.0 - buy_fees - sell_fees)
    assert ledger.cash == pytest.approx(100_000 + ledger.realized)
    assert ledger.position_rows() == [] and ledger.held_qty("IMCC") == 0
    fills = [e for e in ledger.events if e["type"] == EVENT_FILLED]
    assert [(e["source"], e["bot_id"]) for e in fills] == [("manual", None), ("bot", "alpha")]
    assert ledger.closed_orders()[0]["fees"]["total"] == pytest.approx(sell_fees)


def test_covering_a_short_realizes_against_the_short_average() -> None:
    ledger = Ledger(100_000, created_ts=T0)
    ledger.place(row(1, side="SELL"), ts=T0, source="manual")
    ledger.fill(1, ts=T0 + 1, price=20.0, basis="quote")
    assert (ledger.held_qty("IMCC"), ledger.avg_cost("IMCC")) == (-10, 20.0)
    ledger.place(row(2, side="BUY"), ts=T0 + 2, source="manual")
    ledger.fill(2, ts=T0 + 3, price=18.0, basis="quote")
    fees = for_fill("SELL", 10, 20.0).total + for_fill("BUY", 10, 18.0).total
    assert ledger.realized == pytest.approx(20.0 - fees)
    assert ledger.cash == pytest.approx(100_000 + ledger.realized)
    assert ledger.held_qty("IMCC") == 0


def test_re_deriving_from_the_events_reproduces_the_state() -> None:
    ledger = Ledger(100_000, created_ts=T0)
    ledger.place(row(1), ts=T0, source="manual")
    ledger.fill(1, ts=T0 + 1, price=10.0, basis="quote")
    ledger.place(row(2, side="SELL", qty=4, typ="LMT", limit=12.0), ts=T0 + 2, source="manual")
    ledger.place(row(3, side="SELL", qty=6, typ="STP", stop=9.0), ts=T0 + 3, source="manual")
    ledger.cancel(3, ts=T0 + 4)
    copy = Ledger(ledger.starting_cash, created_ts=ledger.created_ts, events=ledger.events)
    assert copy.snapshot("paper") == ledger.snapshot("paper")
    assert copy.closed_orders() == ledger.closed_orders()


def test_unwind_to_forgets_what_happened_after_the_playhead() -> None:
    ledger = Ledger(100_000, created_ts=T0)
    ledger.place(row(1), ts=T0, source="manual")
    ledger.fill(1, ts=T0 + 5, price=10.0, basis="last_print")
    ledger.place(row(2, side="SELL", qty=5, typ="LMT", limit=12.0, ts=T0 + 8), ts=T0 + 8, source="manual")
    assert ledger.working_symbols() == ["IMCC"]
    assert ledger.unwind_to(T0 + 6) == 1
    assert ledger.working_orders() == [] and ledger.held_qty("IMCC") == 10
    assert ledger.unwind_to(T0 + 2) == 1
    assert [r["status"] for r in ledger.working_orders()] == ["Submitted"]
    assert ledger.held_qty("IMCC") == 0 and ledger.cash == 100_000


def test_buying_power_refuses_an_opening_order_but_never_a_reducing_sell() -> None:
    ledger = Ledger(10_000, created_ts=T0)  # below the PDT line: 2x -> 20,000 of power
    assert ledger.can_afford("IMCC", "BUY", 3000, 10.0) == (False, 30_000.0, 20_000.0)
    ledger.place(row(1, qty=1000), ts=T0, source="manual")
    ledger.fill(1, ts=T0 + 1, price=10.0, basis="quote")
    assert ledger.can_afford("IMCC", "BUY", 5000, 10.0)[0] is False
    ok, needed, _available = ledger.can_afford("IMCC", "SELL", 1000, 1.0)
    assert ok is True and needed == 0.0


def test_rollover_records_the_day_start_equity_and_resets_the_day_figures() -> None:
    ledger = Ledger(100_000, created_ts=T0)
    ledger.place(row(1), ts=T0, source="manual")
    ledger.fill(1, ts=T0 + 1, price=10.0, basis="quote")
    ledger.mark("IMCC", 12.0)
    snap = ledger.snapshot("paper")
    assert (snap["fills_today"], snap["commissions_today"]) == (1, 1.0)
    assert snap["day_pnl"] == pytest.approx(20.0 - 1.0)
    next_day = T0 + 24 * 3600
    assert ledger.rollover(next_day) is True
    assert ledger.day_started_ts == day_start_ts(next_day)
    assert ledger.day_start_equity == pytest.approx(ledger.net_liquidation())
    later = ledger.snapshot("paper")
    assert (later["fills_today"], later["commissions_today"], later["day_pnl"]) == (0, 0.0, 0.0)
    assert later["day_started_et"].startswith("2026-09-22T04:00:00")
    assert ledger.rollover(next_day + 60) is False


def test_snapshot_carries_exactly_the_contract_fields() -> None:
    ledger = Ledger(100_000, created_ts=T0)
    ledger.place(row(1), ts=T0, source="manual")
    ledger.fill(1, ts=T0 + 1, price=10.0, basis="quote")
    ledger.place(row(2, side="SELL", typ="LMT", limit=12.0), ts=T0 + 2, source="manual")
    paper = ledger.snapshot("paper")
    assert set(paper) == CONTRACT
    assert paper["account_id"] == "NOVA-PAPER" and paper["schema_version"] == 1
    assert [set(p) for p in paper["positions"]] == [{"symbol", "qty", "avg_cost", "mark", "unrealized"}]
    assert [w["order_id"] for w in paper["working"]] == [2]
    sim = ledger.snapshot("sim", replay_key=("historical", "IMCC"))
    assert set(sim) == CONTRACT | {"replay_key"}
    assert (sim["account_id"], sim["replay_key"]) == ("NOVA-SIM", ["historical", "IMCC"])
