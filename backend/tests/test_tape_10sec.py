"""Tape prints must build live 10Sec OHLCV bars without reqHistoricalData (D-003)."""
from __future__ import annotations

import archive.db as archive_db
import archive.write_queue as wq
import bars_store
from constants_tape import TAPE_10SEC_FLUSH_GRACE_SEC
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

    tape_10sec.flush_elapsed(bucket_ts + 10.0 + TAPE_10SEC_FLUSH_GRACE_SEC - 1.0)
    assert wq.pending() == 0  # elapsed, but a late print may still land in it

    tape_10sec.flush_elapsed(bucket_ts + 10.0 + TAPE_10SEC_FLUSH_GRACE_SEC)
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
    tape_10sec.flush_elapsed(t0 + 10.0 + TAPE_10SEC_FLUSH_GRACE_SEC)
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


def test_cold_10sec_paints_tape_bars_and_asks_as_an_open_chart_until_history_lands(
    monkeypatch, tmp_path,
):
    """D-003: a cold 10Sec pane cannot sit empty after a flushed tape bucket.

    Empty interactive /bars must ask ``open_chart``. After one provisional
    candle lands, /bars returns it (not []) and still asks ``open_chart``:
    tape-built rows are not the pane's history, and a "warm" ask was shed at
    the reserve and never sent again (RIOX 2026-11-04). Once a fill has
    landed this session, the pane's refresh is "warm".
    """
    import time as _time
    from unittest.mock import patch

    import chart_bars

    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()
    t0 = 1_700_000_000.0
    monkeypatch.setattr(chart_bars, "_session_start", lambda now: t0 - 3600)

    with patch.object(chart_bars._ibkr_client, "is_ready", return_value=True):
        with patch.object(chart_bars, "_schedule_ibkr_fill") as fill:
            empty = chart_bars.fetch_chart_bars(
                "MSS",
                "10Sec",
                1500,
                discovery_provider="ibkr",
                interactive=True,
            )
    assert empty["bars"] == []
    assert empty["coverage"]["filling"] is True
    fill.assert_called_once()
    assert fill.call_args.kwargs["priority"] == "open_chart"

    tape_10sec.on_print("mss", 1.66, 100, t0)
    tape_10sec.flush_elapsed(t0 + 10.0 + TAPE_10SEC_FLUSH_GRACE_SEC)
    wq.drain_once()

    stored = bars_store.read("MSS", "10Sec", 1500)
    assert stored is not None
    assert len(stored["bars"]) == 1
    assert bars_store.store_series_complete("10Sec", len(stored["bars"])) is False

    with patch.object(chart_bars._ibkr_client, "is_ready", return_value=True):
        with patch.object(chart_bars, "_schedule_ibkr_fill") as fill:
            out = chart_bars.fetch_chart_bars(
                "MSS",
                "10Sec",
                1500,
                discovery_provider="ibkr",
                interactive=True,
            )
    assert len(out["bars"]) == 1
    assert out["bars"][0]["c"] == 1.66
    assert out["coverage"]["filling"] is True
    assert out["coverage"]["history_pending"] is True
    fill.assert_called_once()
    assert fill.call_args.kwargs["priority"] == "open_chart"

    hist = [{"t": "2023-11-14T22:13:30Z", "o": 1.6, "h": 1.7, "l": 1.6, "c": 1.7, "v": 900}]
    bars_store.write_payload({
        "symbol": "MSS", "timeframe": "10Sec", "bars": hist,
        "coverage": {**bars_store.coverage_from_bars(hist, filling=False), "fetched_ts": _time.time()},
    })
    with patch.object(chart_bars._ibkr_client, "is_ready", return_value=True):
        with patch.object(chart_bars, "_schedule_ibkr_fill") as fill:
            after = chart_bars.fetch_chart_bars(
                "MSS", "10Sec", 1500, discovery_provider="ibkr", interactive=True,
            )
    assert after["coverage"]["history_pending"] is False
    fill.assert_called_once()  # two bars are not a complete series
    assert fill.call_args.kwargs["priority"] == "warm"


def test_the_10sec_pane_reads_todays_session_only(monkeypatch, tmp_path):
    """RIOX 2026-11-04: 11-03's 10-second tape bars at $9.13 drew beside today's at $13.70, the price axis
    ran $9-$15 and today's candles lay flat. The pane reads from the session's 04:00 ET; other panes do not."""
    from unittest.mock import patch

    import chart_bars

    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()
    session_start = 1_793_782_800.0  # 2026-11-04 04:00 ET
    yesterday = session_start - 60_220  # 2026-11-03 11:16:20 ET
    today = session_start + 16_320  # 2026-11-04 08:32:00 ET
    tape_10sec.on_print("riox", 9.13, 100, yesterday)
    tape_10sec.on_print("riox", 13.70, 500, today)
    tape_10sec.flush_elapsed(today + 10.0 + TAPE_10SEC_FLUSH_GRACE_SEC)
    wq.enqueue_intraday_bar(
        symbol="RIOX", ts=yesterday - 20, open_=9.1, high=9.2, low=9.1, close=9.13, volume=100.0,
        timeframe="1Min",
    )
    wq.drain_once()
    assert len(bars_store.read("RIOX", "10Sec", 1500)["bars"]) == 2

    monkeypatch.setattr(chart_bars, "_session_start", lambda now: session_start)
    with patch.object(chart_bars._ibkr_client, "is_ready", return_value=True):
        with patch.object(chart_bars, "_schedule_ibkr_fill"):
            ten = chart_bars.fetch_chart_bars("RIOX", "10Sec", 1500, discovery_provider="ibkr", interactive=True)
            minute = chart_bars.fetch_chart_bars("RIOX", "1Min", 1000, discovery_provider="ibkr", interactive=True)
    assert [b["c"] for b in ten["bars"]] == [13.70]
    assert ten["coverage"]["as_of"] == "2026-11-04T13:32:00Z"
    assert [b["c"] for b in minute["bars"]] == [9.13]


def test_a_print_lands_in_the_candle_of_ibkrs_own_second(monkeypatch, tmp_path):
    """#721: IBKR's historical 10-second bars are keyed by its second, so a print that arrived
    0.6 s after the boundary belongs to the candle before it, as IBKR's own bar will say."""
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()

    b = 1_700_000_040.0
    tape_10sec.on_print("veea", 2.00, 100, b + 3.2, b + 3)
    tape_10sec.on_print("veea", 2.05, 300, b + 10.6, b + 9)    # arrived after the boundary
    tape_10sec.on_print("veea", 2.10, 50, b + 11.0, b + 10)     # the next candle opens
    wq.drain_once()
    bar = bars_store.read("VEEA", "10Sec", 10)["bars"][0]
    assert (bar["o"], bar["h"], bar["c"], bar["v"]) == (2.00, 2.05, 2.05, 400)


def test_a_closed_candle_is_never_reopened(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()

    b = 1_700_000_040.0
    tape_10sec.on_print("veea", 2.00, 100, b + 1.0, b + 1)
    tape_10sec.flush_elapsed(b + 10.0 + TAPE_10SEC_FLUSH_GRACE_SEC)
    assert wq.pending() == 1
    tape_10sec.on_print("veea", 1.50, 9_000, b + 30.0, b + 2)   # later than the grace: dropped
    tape_10sec.flush_elapsed(b + 60.0)
    assert wq.pending() == 1                                     # nothing new to store


def test_without_ibkrs_second_the_arrival_keys_the_candle(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    tape_10sec.reset_for_tests()

    b = 1_700_000_040.0
    tape_10sec.on_print("veea", 2.00, 100, b + 3.0)
    tape_10sec.on_print("veea", 2.05, 100, b + 10.5, None)
    wq.drain_once()
    assert bars_store.read("VEEA", "10Sec", 10)["bars"][0]["v"] == 100
