"""exchange_ts_unix must not treat Unix-epoch datetimes as real trade time."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr.ticks_handler import exchange_ts_unix


def test_epoch_datetime_falls_through_to_wall_clock(monkeypatch):
    monkeypatch.setattr("ibkr.ticks_handler.time.time", lambda: 1_700_000_123.0)
    ticker = SimpleNamespace(
        lastTimestamp=None,
        rtTime=None,
        time=datetime(1970, 1, 1, tzinfo=timezone.utc),
    )
    assert exchange_ts_unix(ticker) == 1_700_000_123.0


def test_sane_unix_int_is_used():
    ticker = SimpleNamespace(lastTimestamp=1_700_000_000, rtTime=None, time=None)
    assert exchange_ts_unix(ticker) == 1_700_000_000.0
