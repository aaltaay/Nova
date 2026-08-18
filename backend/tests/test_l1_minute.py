"""Scanner L1 must build live 1Min bars in bars_intraday without IB historicals."""
from __future__ import annotations

import archive.db as archive_db
import archive.write_queue as wq
import bars_store
import ibkr.l1_minute as l1_minute
from ibkr import scanner_l1


def test_same_minute_aggregates_ohlc(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    t0 = 1_700_000_040.0  # 40s into a minute
    l1_minute.on_last("pfsa", 10.0, t0)
    l1_minute.on_last("pfsa", 12.0, t0 + 5.0)
    l1_minute.on_last("pfsa", 9.5, t0 + 10.0)
    l1_minute.on_last("pfsa", 11.0, t0 + 15.0)
    assert wq.pending() == 0  # current minute stays in memory

    l1_minute.on_last("pfsa", 11.2, t0 + 60.0)  # next minute -- flush prior
    assert wq.pending() == 1
    wq.drain_once()

    hit = bars_store.read("PFSA", "1Min", 10)
    assert hit is not None
    assert len(hit["bars"]) == 1
    bar = hit["bars"][0]
    assert bar["o"] == 10.0
    assert bar["h"] == 12.0
    assert bar["l"] == 9.5
    assert bar["c"] == 11.0
    assert bar["v"] == 0


def test_live_minute_does_not_mark_series_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    t0 = 1_700_000_000.0
    l1_minute.on_last("aixc", 1.0, t0)
    l1_minute.on_last("aixc", 1.1, t0 + 60.0)
    wq.drain_once()
    hit = bars_store.read("AIXC", "1Min", 100)
    assert hit is not None
    assert bars_store.store_series_complete("1Min", len(hit["bars"])) is False
    conn = archive_db.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM bars_coverage WHERE symbol='AIXC'",
        ).fetchone()
    finally:
        conn.close()
    assert row["c"] == 0
    # No hist coverage row -- do not pretend this is a finished fill.
    assert hit["coverage"]["filling"] is True


def test_elapsed_minute_flushes_without_next_print(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    minute_ts = 1_700_000_040.0 - (1_700_000_040.0 % 60.0)
    l1_minute.on_last("aaoz", 2.0, minute_ts + 10.0)
    assert wq.pending() == 0

    l1_minute.flush_elapsed(minute_ts + 59.0)
    assert wq.pending() == 0

    l1_minute.flush_elapsed(minute_ts + 60.0)
    assert wq.pending() == 1
    wq.drain_once()
    hit = bars_store.read("AAOZ", "1Min", 10)
    assert hit is not None
    assert hit["bars"][0]["c"] == 2.0

    l1_minute.flush_elapsed(minute_ts + 120.0)
    assert wq.pending() == 0


def test_on_l1_quote_enqueues_without_sqlite(monkeypatch, tmp_path):

    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    opened: list[str] = []
    real = archive_db.get_connection

    def _spy():
        opened.append("get_connection")
        return real()

    monkeypatch.setattr(archive_db, "get_connection", _spy)
    scanner_l1.on_l1_quote("CAST", 2.10, 1000, 1.90, 1_700_000_000.0)
    scanner_l1.on_l1_quote("CAST", 2.20, 1100, 1.90, 1_700_000_060.0)
    assert opened == []
    assert wq.pending() == 1
