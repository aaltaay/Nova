"""Whose each journal trade is (ADR 069 decision 6, #1267): an IBKR round trip takes the holder of the order that
opened it, an imported file is yours, and a journal from before migrates in place -- its rows stay null and read
as yours, and a file read as it is answers without the new columns."""
from __future__ import annotations

import sqlite3

import pytest

import execution.store as exec_store
import execution.telemetry as telemetry
import journal.db as journal_db
import journal.round_trip as round_trip
from journal import store
from journal.import_apply import apply_parsed_trades

T0 = 1_790_000_000.0

# The trades table as it first shipped: none of the columns added since.
_OLD_TRADES = """
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, opened_ts REAL NOT NULL, closed_ts REAL, symbol TEXT NOT NULL,
    setup TEXT, side TEXT NOT NULL, qty INTEGER NOT NULL, entry_price REAL NOT NULL, exit_price REAL,
    stop_price REAL, target_price REAL, pnl REAL, adherent INTEGER, notes TEXT
);
INSERT INTO trades (opened_ts, closed_ts, symbol, side, qty, entry_price, exit_price, pnl)
VALUES (1790000000.0, 1790000060.0, 'OLD', 'long', 10, 1.0, 1.5, 5.0);
"""
# The columns added before ADR 069: a desk's journal the day before this change.
_BEFORE_OWNERS = """
ALTER TABLE trades ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0;
ALTER TABLE trades ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';
ALTER TABLE trades ADD COLUMN close_key TEXT;
ALTER TABLE trades ADD COLUMN commission REAL;
ALTER TABLE trades ADD COLUMN fill_ids TEXT;
"""


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(exec_store, "cache_dir", lambda: tmp_path)
    round_trip.reset_for_tests()
    telemetry.reset_for_tests()
    yield tmp_path
    round_trip.reset_for_tests()
    telemetry.reset_for_tests()


def _old_journal(path, *, before_owners: bool = False) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_OLD_TRADES + (_BEFORE_OWNERS if before_owners else ""))
    conn.commit()
    conn.close()


def _columns(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
    finally:
        conn.close()


def test_an_old_journal_migrates_in_place_and_its_rows_read_as_yours(isolated_dbs) -> None:
    path = isolated_dbs / "journal.db"
    _old_journal(path)
    journal_db.init_db()
    assert {"venue", "owner", "bot", "close_key", "tags"} <= _columns(path)
    (old,) = store.get_closed_trades()
    assert (old["symbol"], old["venue"], old["owner"], old["bot"], old["pnl"]) == ("OLD", None, None, None, 5.0)
    assert [t["symbol"] for t in store.get_closed_trades(owner="you")] == ["OLD"]
    assert store.get_closed_trades(owner="claude") == []
    assert store.get_closed_trades(venue="paper") == []
    journal_db.init_db()                                         # safe to run again
    assert len(store.get_closed_trades()) == 1


def test_a_journal_read_as_it_is_answers_without_the_new_columns(tmp_path) -> None:
    path = tmp_path / "research" / "journal.db"
    path.parent.mkdir()
    _old_journal(path, before_owners=True)
    (row,) = store.get_trades(database=path)
    assert (row["symbol"], row["venue"], row["owner"], row["bot"]) == ("OLD", None, None, None)
    assert store.get_trades(database=path, owner="you")[0]["symbol"] == "OLD"
    assert store.get_trades(database=path, venue="paper") == []
    assert store.get_trades(database=path, owner="earlier_bots") == []
    assert "venue" not in _columns(path)                         # read, never migrated


def _watch_fill(idempotency_key: str, order_id: int, side: str, price: float, *, source: str,
                origin: str | None) -> str:
    exec_id, _ = exec_store.reserve(
        idempotency_key=idempotency_key, operation="place", source=source, symbol="IVF", received_ns=order_id,
        payload={"side": side, "qty": 1, "origin": origin},
    )
    exec_store.update_stages(exec_id, order_id=order_id, status="sent")
    watch = telemetry.watch_order(order_id, exec_id, side=side)
    watch.note_status("Filled", filled=1.0, remaining=0.0, average_fill_price=price)
    watch.note_execution(avg_price=price, price=price, shares=1.0, cumulative_shares=1.0)
    watch.note_filled()
    return exec_id


@pytest.mark.parametrize(("source", "origin", "whose"), [
    ("manual", "ticket", ("you", None)),
    ("bot", "live_trader", ("earlier_bots", "live_trader")),
])
def test_an_ibkr_round_trip_is_the_opening_orders_holders(source, origin, whose) -> None:
    journal_db.init_db()
    exec_store.init_db()
    _watch_fill("open", 19085, "BUY", 3.5, source=source, origin=origin)
    _watch_fill("close", 19112, "SELL", 4.25, source="flatten", origin=None)   # Nova's close names no one
    (trade,) = store.get_closed_trades()
    assert (trade["owner"], trade["bot"], trade["venue"]) == (*whose, None)


def test_an_imported_file_is_yours() -> None:
    journal_db.init_db()
    result = apply_parsed_trades([{
        "symbol": "IMP", "side": "long", "qty": 100, "entry_price": 10.0, "exit_price": 10.5, "pnl": 48.0,
        "opened_ts": T0, "closed_ts": T0 + 60, "tags": ["import"],
    }], source="csv")
    assert result["imported"] == 1
    (trade,) = store.get_closed_trades()
    assert (trade["owner"], trade["bot"], trade["venue"]) == ("you", None, None)
