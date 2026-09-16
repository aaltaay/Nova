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


def test_l1_upsert_does_not_clobber_hist_ohlc(monkeypatch, tmp_path):
    """Charts read this table. L1 last is not a trade bar -- never rewrite hist."""
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    ts = 1_700_000_040.0 - (1_700_000_040.0 % 60.0)
    bars_store.write_payload({
        "symbol": "AIXC",
        "timeframe": "1Min",
        "source": "ibkr",
        "bars": [{
            "t": ts, "o": 1.20, "h": 1.40, "l": 1.10, "c": 1.35, "v": 2938,
        }],
        "coverage": bars_store.coverage_from_bars(
            [{"t": ts, "o": 1.20, "h": 1.40, "l": 1.10, "c": 1.35, "v": 2938}],
            filling=False,
        ),
    })

    l1_minute.on_last("aixc", 9.99, ts + 10.0)
    l1_minute.flush_elapsed(ts + 60.0)
    wq.drain_once()

    hit = bars_store.read("AIXC", "1Min", 10)
    assert hit is not None
    bar = hit["bars"][0]
    assert bar["o"] == 1.20
    assert bar["h"] == 1.40
    assert bar["l"] == 1.10
    assert bar["c"] == 1.35
    assert bar["v"] == 2938
    assert hit["coverage"]["filling"] is False


def _hist_payload(symbol: str, ts: float, *, volume: float) -> dict:
    bar = {"t": ts, "o": 1.20, "h": 1.40, "l": 1.10, "c": 1.35, "v": volume}
    return {
        "symbol": symbol,
        "timeframe": "1Min",
        "source": "ibkr",
        "bars": [bar],
        "coverage": bars_store.coverage_from_bars([bar], filling=False),
    }


def test_l1_does_not_clobber_zero_volume_hist(monkeypatch, tmp_path):
    """IB hist minutes can be volume=0 (halt / illiquid AH). Volume is not ownership."""
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    ts = 1_700_000_040.0 - (1_700_000_040.0 % 60.0)
    bars_store.write_payload(_hist_payload("AIXC", ts, volume=0))

    l1_minute.on_last("aixc", 9.99, ts + 10.0)
    l1_minute.flush_elapsed(ts + 60.0)
    wq.drain_once()

    bar = bars_store.read("AIXC", "1Min", 10)["bars"][0]
    assert bar["o"] == 1.20
    assert bar["h"] == 1.40
    assert bar["l"] == 1.10
    assert bar["c"] == 1.35
    assert bar["v"] == 0
    conn = archive_db.get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) AS c FROM bars_intraday").fetchone()["c"]
        source = conn.execute("SELECT source FROM bars_intraday").fetchone()["source"]
    finally:
        conn.close()
    assert n == 1
    assert source == "ibkr"


def test_l1_volume_cannot_buy_a_hist_row(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()

    ts = 1_700_000_000.0
    bars_store.write_payload(_hist_payload("CAST", ts, volume=2938))
    wq.enqueue_intraday_bar(
        symbol="CAST", ts=ts, open_=9.0, high=9.99, low=8.0,
        close=9.5, volume=50_000.0, timeframe="1Min",
    )
    wq.drain_once()

    bar = bars_store.read("CAST", "1Min", 10)["bars"][0]
    assert bar["h"] == 1.40
    assert bar["c"] == 1.35
    assert bar["v"] == 2938
    conn = archive_db.get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) AS c FROM bars_intraday").fetchone()["c"]
    finally:
        conn.close()
    assert n == 1


def test_hist_fill_replaces_live_minute(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    ts = 1_700_000_040.0 - (1_700_000_040.0 % 60.0)
    l1_minute.on_last("cdtg", 3.00, ts + 10.0)
    l1_minute.flush_elapsed(ts + 60.0)
    wq.drain_once()
    assert bars_store.read("CDTG", "1Min", 10)["bars"][0]["c"] == 3.00

    bars_store.write_payload(_hist_payload("CDTG", ts, volume=4100))
    hit = bars_store.read("CDTG", "1Min", 10)
    assert len(hit["bars"]) == 1
    bar = hit["bars"][0]
    assert bar["o"] == 1.20
    assert bar["h"] == 1.40
    assert bar["c"] == 1.35
    assert bar["v"] == 4100
    conn = archive_db.get_connection()
    try:
        sources = [
            r["source"] for r in conn.execute("SELECT source FROM bars_intraday")
        ]
    finally:
        conn.close()
    assert sources == ["ibkr"]


def test_volume_increment_baselines_then_deltas():
    assert l1_minute.volume_increment(None, size=100, cum_volume=5_000_000) == (
        100.0, 5_000_000.0,
    )
    assert l1_minute.volume_increment(5_000_000.0, size=50, cum_volume=5_000_400) == (
        400.0, 5_000_400.0,
    )
    assert l1_minute.volume_increment(5_000_400.0, size=50, cum_volume=5_000_400) == (
        0.0, 5_000_400.0,
    )
    assert l1_minute.volume_increment(None, size=75, cum_volume=None) == (75.0, None)
    # Session reset: cumulative drops; keep this print, do not go negative.
    assert l1_minute.volume_increment(5_000_400.0, size=80, cum_volume=120) == (
        80.0, 120.0,
    )


def test_l1_minute_stamps_cum_volume_delta(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    t0 = 1_700_000_040.0
    l1_minute.on_last("pfsa", 10.0, t0, size=100, cum_volume=1_000_000)
    l1_minute.on_last("pfsa", 10.2, t0 + 10.0, size=50, cum_volume=1_000_350)
    l1_minute.on_last("pfsa", 10.1, t0 + 60.0, size=25, cum_volume=1_000_400)
    wq.drain_once()

    bar = bars_store.read("PFSA", "1Min", 10)["bars"][0]
    assert bar["v"] == 450  # 100 first print + 350 delta; next-minute 25 stays open
    assert bar["c"] == 10.2


def test_l1_minute_stamped_volume_moves_vwap_vs_zero_overlay(monkeypatch, tmp_path):
    """sessionVwapPoints skips volume=0, so a stamped overlay must move the tip."""
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    t0 = 1_700_000_000.0
    l1_minute.on_last("aixc", 10.0, t0, size=1_000, cum_volume=1_000)
    l1_minute.on_last("aixc", 10.0, t0 + 30.0, size=1_000, cum_volume=2_000)
    l1_minute.on_last("aixc", 20.0, t0 + 60.0, size=2_000, cum_volume=4_000)
    l1_minute.on_last("aixc", 20.0, t0 + 120.0, size=1, cum_volume=4_001)
    wq.drain_once()

    bars = bars_store.read("AIXC", "1Min", 10)["bars"]
    assert [b["v"] for b in bars] == [2000, 2000]

    def _hlc3_vwap(rows):
        num = den = 0.0
        tip = None
        for row in rows:
            vol = float(row["v"])
            if vol <= 0:
                continue
            typical = (row["h"] + row["l"] + row["c"]) / 3.0
            num += typical * vol
            den += vol
            tip = num / den
        return tip

    zero_overlay = [
        {"h": 10.0, "l": 10.0, "c": 10.0, "v": 2000},
        {"h": 20.0, "l": 20.0, "c": 20.0, "v": 0},
    ]
    assert _hlc3_vwap(zero_overlay) == 10.0
    assert _hlc3_vwap(bars) == 15.0


def test_l1_upsert_can_refine_live_only_row(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()

    ts = 1_700_000_040.0 - (1_700_000_040.0 % 60.0)
    wq.enqueue_intraday_bar(
        symbol="CDTG", ts=ts, open_=3.00, high=3.10, low=2.90,
        close=3.05, volume=0.0, timeframe="1Min",
    )
    wq.drain_once()
    wq.enqueue_intraday_bar(
        symbol="CDTG", ts=ts, open_=3.20, high=3.50, low=2.80,
        close=3.40, volume=0.0, timeframe="1Min",
    )
    wq.drain_once()

    hit = bars_store.read("CDTG", "1Min", 10)
    bar = hit["bars"][0]
    assert hit["source"] == "ibkr"
    assert bar["o"] == 3.00  # first open sticks
    assert bar["h"] == 3.50
    assert bar["l"] == 2.80
    assert bar["c"] == 3.40
    assert bar["v"] == 0
    conn = archive_db.get_connection()
    try:
        tagged = conn.execute("SELECT source FROM bars_intraday").fetchone()["source"]
    finally:
        conn.close()
    assert tagged == "ibkr_l1"
