"""Paper ledger on disk: atomic writes, loud refusal, archive instead of delete."""
from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from practice import persist
from practice.clock import ET
from practice.ledger import Ledger

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=ET).timestamp()


def _ledger_with_history() -> Ledger:
    ledger = Ledger(100_000, created_ts=T0)
    ledger.place(
        {"order_id": 1, "symbol": "IMCC", "side": "BUY", "qty": 10.0, "filled_qty": 0.0,
         "remaining_qty": 10.0, "order_type": "MKT", "limit_price": None, "stop_price": None,
         "status": "Submitted", "placed_ts": T0, "source": "nova", "order_source": "manual",
         "bot_id": None},
        ts=T0, source="manual",
    )
    ledger.fill(1, ts=T0 + 1, price=10.0, basis="quote")
    return ledger


def test_round_trip_preserves_events_and_derived_state(tmp_path) -> None:
    ledger = _ledger_with_history()
    path = str(tmp_path / "practice-paper.json")
    persist.save(ledger, path)
    back = persist.load(path)
    assert back is not None
    assert back.events == ledger.events
    assert back.snapshot("paper") == ledger.snapshot("paper")
    assert json.loads(open(path, encoding="utf-8").read())["schema_version"] == 1
    assert [f for f in os.listdir(tmp_path) if f.endswith(".tmp")] == []


def test_a_missing_file_loads_as_none(tmp_path) -> None:
    assert persist.load(str(tmp_path / "practice-paper.json")) is None


def test_an_unknown_schema_version_is_refused_loud(tmp_path) -> None:
    path = tmp_path / "practice-paper.json"
    path.write_text(json.dumps({"schema_version": 99, "starting_cash": 1, "created_ts": T0, "events": []}))
    with pytest.raises(persist.LedgerSchemaError, match="schema_version 99"):
        persist.load(str(path))


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        json.dumps([1, 2, 3]),
        json.dumps({"schema_version": "x", "starting_cash": 1, "created_ts": T0, "events": []}),
        json.dumps({"schema_version": 1, "starting_cash": 1, "created_ts": T0, "events": [{"type": "bogus", "ts": 1}]}),
        json.dumps({"schema_version": 1, "starting_cash": -5, "created_ts": T0, "events": []}),
    ],
)
def test_a_malformed_ledger_is_refused_not_guessed_at(tmp_path, body) -> None:
    path = tmp_path / "practice-paper.json"
    path.write_text(body)
    with pytest.raises(persist.LedgerSchemaError):
        persist.load(str(path))


def test_archive_stamps_the_old_file_and_never_overwrites_an_earlier_archive(tmp_path) -> None:
    path = tmp_path / "practice-paper.json"
    now = datetime(2026, 9, 21, 9, 30, 0, tzinfo=ET)
    assert persist.archive(str(path)) is None
    path.write_text("{}")
    first = persist.archive(str(path), now=now)
    assert first is not None and first.endswith("practice-paper-20260921-093000.json")
    path.write_text("{}")
    second = persist.archive(str(path), now=now)
    assert second is not None and second.endswith("practice-paper-20260921-093000-1.json")
    assert os.path.exists(first) and os.path.exists(second) and not path.exists()
