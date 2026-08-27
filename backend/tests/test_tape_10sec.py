"""Tape prints must build live 10Sec OHLCV bars without reqHistoricalData (D-003)."""
from __future__ import annotations

import archive.db as archive_db
import archive.write_queue as wq
import bars_store
from ibkr import tape_10sec


def test_prints_across_10s_boundary_flush_closed_bucket(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()

    t0 = 1_700_000_040.0  # inside a 10s bucket (40-50s)
    tape_10sec.on_print("mss", 1.66, 100, t0)
    tape_10sec.on_print("mss", 1.67, 650, t0 + 3.0)
    tape_10sec.on_print("mss", 1.65, 200, t0 + 6.0)
    assert wq.pending() == 0  # current bucket stays in memory

    tape_10sec.on_print("mss", 1.68, 50, t0 + 10.0)  # next bucket -- flush prior
    assert wq.pending() == 1
    wq.drain_once()

    hit = bars_store.read("MSS", "10Sec", 10)
    assert hit is not None
    assert len(hit["bars"]) == 1
    bar = hit["bars"][0]
    assert bar["o"] == 1.66
    assert bar["h"] == 1.67
    assert bar["l"] == 1.65
    assert bar["c"] == 1.65
    assert bar["v"] == 950  # 100 + 650 + 200


def test_quiet_symbol_flushes_via_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()

    bucket_ts = 1_700_000_040.0 - (1_700_000_040.0 % 10.0)
    tape_10sec.on_print("cdtg", 3.0, 10, bucket_ts + 3.0)
    assert wq.pending() == 0

    tape_10sec.flush_elapsed(bucket_ts + 9.0)
    assert wq.pending() == 0  # bucket not elapsed yet

    tape_10sec.flush_elapsed(bucket_ts + 10.0)
    assert wq.pending() == 1
    wq.drain_once()
    hit = bars_store.read("CDTG", "10Sec", 10)
    assert hit is not None
    assert hit["bars"][0]["c"] == 3.0

    tape_10sec.flush_elapsed(bucket_ts + 30.0)
    assert wq.pending() == 0  # already flushed, nothing left open


def test_rows_carry_ibkr_l1_source_and_10sec_timeframe(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()

    t0 = 1_700_000_000.0
    tape_10sec.on_print("aixc", 9.99, 25, t0)
    tape_10sec.flush_elapsed(t0 + 10.0)
    wq.drain_once()

    conn = archive_db.get_connection()
    try:
        row = conn.execute(
            "SELECT symbol, timeframe, source, volume FROM bars_intraday "
            "WHERE symbol='AIXC'",
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["timeframe"] == "10Sec"
    assert row["source"] == "ibkr_l1"
    assert row["volume"] == 25

    # A tape-only bucket must not fake completeness -- the hist fill still
    # needs to run (IBKR_BARS_STORE_MIN_BARS["10Sec"] == 100 bars).
    hit = bars_store.read("AIXC", "10Sec", 10)
    assert bars_store.store_series_complete("10Sec", len(hit["bars"])) is False
    assert hit["coverage"]["filling"] is True


def test_ignores_non_positive_price_and_timestamp():
    tape_10sec.reset_for_tests()
    tape_10sec.on_print("zzzz", 0.0, 100, 1_700_000_000.0)
    tape_10sec.on_print("zzzz", 1.0, 100, 0.0)
    tape_10sec.on_print("", 1.0, 100, 1_700_000_000.0)
    assert tape_10sec._open == {}
