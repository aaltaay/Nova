"""Prints reported for volume only never set a candle's price (operator report 2026-09-23).

PLTR's 10-second pane grew wicks $2-3 under the market that IBKR's own bars
(and every other chart) left out: FINRA ``4 W`` (derivatively priced, average
price) and odd-lot prints. The prints below are the recorded ones.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import ibkr.tape_stream as tape
from sale_conditions import row_sets_price, sets_price


@pytest.mark.parametrize("conditions", ["", " F  ", "  T ", " FT ", " O X", " 5 X", "    "])
def test_regular_intermarket_sweep_and_extended_hours_prints_set_a_price(conditions):
    assert sets_price(conditions) is True


@pytest.mark.parametrize("conditions", [
    "   I",   # odd lot
    " F I",   # odd lot, intermarket sweep
    "  TI",   # odd lot, extended hours
    " 4 W",   # derivatively priced, average price (the PLTR wick)
    " 4 I",
    " 4  ",   # derivatively priced alone (IBKR's bars leave it out)
    "   P",   # prior reference price (a GRML print $2.31 under the market)
    "C  I",
    "R T ",   # seller
    " 7 V",   # contingent
    "4 W",    # unpadded, as the archive stores it
])
def test_volume_only_prints_never_set_a_price(conditions):
    assert sets_price(conditions) is False


def test_ibkr_unreported_flag_wins_over_clean_conditions():
    # CTA reports an average-price trade as ``B``, which UTP uses for a bunched
    # trade -- only IBKR's own flag can tell them apart.
    assert sets_price("  TB", unreported=True) is False
    assert sets_price("  TB", unreported=False) is True


def test_row_verdict_prefers_its_stamp_then_its_conditions():
    assert row_sets_price({"conditions": "", "sets_price": False}) is False
    assert row_sets_price({"conditions": " 4 W", "sets_price": True}) is True
    assert row_sets_price({"conditions": " 4 W"}) is False
    assert row_sets_price({"conditions": "", "unreported": True}) is False
    assert row_sets_price({"price": 10.0}) is True  # a pre-stamp row with no conditions


class _FakeTicker:
    def __init__(self, ticks):
        self.tickByTicks = list(ticks)


def _tbt(ts, price, size, exchange, conditions, unreported=False):
    return SimpleNamespace(
        time=datetime.fromtimestamp(ts, tz=timezone.utc), price=price, size=size,
        exchange=exchange, specialConditions=conditions,
        tickAttribLast=SimpleNamespace(pastLimit=False, unreported=unreported),
    )


def test_live_tape_lists_every_print_but_candles_take_only_prices(monkeypatch):
    q: asyncio.Queue = asyncio.Queue()
    monkeypatch.setitem(tape._viewer_queues, "PLTR", [q])
    monkeypatch.setattr(tape._depth, "current_book", lambda _sym: {
        "bids": [{"price": 192.64, "size": 100}], "asks": [{"price": 192.80, "size": 100}],
    })
    monkeypatch.setattr("archive.write_queue.enqueue_tape_print", lambda **_kw: None)
    monkeypatch.setattr("ibkr.tape_recording.dispatch", lambda _payload: None)
    minute: list[float] = []
    ten_sec: list[float] = []
    monkeypatch.setattr("archive.bar_builder.on_tape_print", lambda **kw: minute.append(kw["price"]))
    monkeypatch.setattr("ibkr.tape_10sec.on_print", lambda _s, price, _z, _t: ten_sec.append(price))

    t0 = 1_790_171_109.0  # 2026-09-23 09:45:09 ET
    tape._on_tape_update(_FakeTicker([
        _tbt(t0, 192.75, 200, "NASDAQ", ""),
        _tbt(t0 + 0.1, 190.38, 100, "FINRA", " 4 W", unreported=True),
        _tbt(t0 + 0.2, 190.37, 1, "FINRA", "   I", unreported=True),
        _tbt(t0 + 0.3, 192.76, 100, "ARCA", " F  "),
    ]), "PLTR")

    listed = [q.get_nowait() for _ in range(q.qsize())]
    assert [p["price"] for p in listed] == [192.75, 190.38, 190.37, 192.76]
    assert [p["sets_price"] for p in listed] == [True, False, False, True]
    assert [p["unreported"] for p in listed] == [False, True, True, False]
    assert minute == [192.75, 192.76]
    assert ten_sec == [192.75, 192.76]


def test_minute_backfill_skips_prints_that_do_not_set_a_price(monkeypatch, tmp_path):
    import archive.bar_builder as bar_builder
    import archive.db as archive_db

    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    m0 = int(1_790_171_100 // 60) * 60
    rows = [
        dict(symbol="PLTR", ts=m0 + 1, price=192.75, size=200, conditions="", source="ibkr"),
        dict(symbol="PLTR", ts=m0 + 9, price=190.38, size=100, conditions="4 W", source="ibkr"),
        dict(symbol="PLTR", ts=m0 + 20, price=192.90, size=40, conditions="I", source="ibkr"),
        dict(symbol="PLTR", ts=m0 + 30, price=192.60, size=300, conditions="F", source="ibkr"),
    ]
    assert bar_builder.backfill_from_tape_rows(rows) == 1
    conn = archive_db.get_connection()
    try:
        bar = conn.execute("SELECT open, high, low, close, volume FROM bars_1m").fetchone()
    finally:
        conn.close()
    assert tuple(bar) == (192.75, 192.75, 192.60, 192.60, 500.0)
    bar_builder.reset_for_tests()


def test_capture_replay_candles_skip_volume_only_prints(monkeypatch):
    from sim import capture_player as player

    player.reset_for_tests()
    start = 1_790_171_100.0
    prints = [
        dict(ts=start + 1, price=192.75, size=200, conditions=""),
        dict(ts=start + 2, price=190.38, size=100, conditions=" 4 W"),
        dict(ts=start + 3, price=192.80, size=100, conditions=" F  "),
    ]
    state = player.CaptureData("2026-09-23|PLTR", "PLTR", prints, [], [],
                               [p["ts"] for p in prints], [], [])
    monkeypatch.setattr(player, "_state", state)
    partial = player.chart_bars("10Sec", 10, asof=start + 5)
    assert partial[-1]["l"] == 192.75 and partial[-1]["v"] == 300
    closed = player.chart_bars("10Sec", 10, asof=start + 10)
    assert closed[-1]["l"] == 192.75 and closed[-1]["h"] == 192.80
    player.reset_for_tests()
