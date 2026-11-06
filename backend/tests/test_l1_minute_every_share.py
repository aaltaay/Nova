"""A live minute keeps every share (operator report, 2026-11-04: "a bunch of volumes that are pointed
towards a zero" on CRIS's 1-minute chart).

``ibkr/l1_minute`` puts an L1 update in the minute of IBKR's last-trade second, which trails the
update's arrival (CRIS that morning: 0.76 s at the median, 13 s at most), while a quiet minute is
written by the desk's clock once it ends. An update that arrived after that opened a fresh bucket
holding only itself, and its write replaced the minute's volume: 174 of CRIS's 271 live minutes held
their last one or two updates' shares -- 04:00 stored 641 while IBKR's day volume grew 130,136. Against
Massive's consolidated tape the stored live minutes held 58% of XLAB's volume (2026-10-16) and 55% of
WETO's (2026-10-15); the L1 line's own day-volume growth matched the tape (median minute 1.000).
"""
from __future__ import annotations

import random
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import archive.db as archive_db
import archive.write_queue as wq
import bars_store
import ibkr.l1_minute as l1_minute
from ibkr.historical_derive import bar_unix

ET = ZoneInfo("America/New_York")
FLUSH_EVERY = 0.35          # IBKR_L1_BATCH_FLUSH_SEC: the scanner flush loop's heartbeat


def at(day: str, hh: int, mm: int, ss: float = 0.0) -> float:
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, hh, mm, tzinfo=ET).timestamp() + ss


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()
    yield
    l1_minute.reset_for_tests()


def _drain() -> None:
    while wq.pending():
        wq.drain_once()


def _bars(symbol: str) -> list[dict]:
    hit = bars_store.read(symbol, "1Min", 1000)
    return hit["bars"] if hit else []


def _ohlcv(bar: dict) -> tuple:
    return bar["o"], bar["h"], bar["l"], bar["c"], bar["v"]


# -- the morning it happened ------------------------------------------------------------------------


def test_an_update_after_its_minute_was_written_joins_it_whole(store):
    """CRIS 04:00: the desk wrote the minute at 04:01:00, then IBKR's 04:00:59 trade arrived."""
    m = at("2026-11-04", 4, 0)
    l1_minute.on_last("cris", 1.05, m + 0, size=500, cum_volume=366_699)     # first: a baseline, its own size
    l1_minute.on_last("cris", 0.99, m + 31, size=2_000, cum_volume=430_000)
    l1_minute.on_last("cris", 0.988, m + 58, size=300, cum_volume=496_194)
    l1_minute.flush_elapsed(m + 60.2)
    l1_minute.on_last("cris", 0.99, m + 59, size=641, cum_volume=496_835)    # stamped 04:00:59, arrived late
    l1_minute.flush_elapsed(m + 60.55)
    _drain()

    bars = _bars("CRIS")
    assert len(bars) == 1
    assert _ohlcv(bars[0]) == (1.05, 1.05, 0.988, 0.99, 500 + 496_835 - 366_699)   # not 641


def test_the_next_minute_writes_a_late_minute_whole(store):
    """The other way the reopened minute was written: the next minute's first update rolled it."""
    m = at("2026-11-04", 7, 20)
    l1_minute.on_last("cris", 1.43, m + 1, size=100, cum_volume=33_399_831)
    l1_minute.on_last("cris", 1.60, m + 50, size=900, cum_volume=34_853_000)
    l1_minute.flush_elapsed(m + 60.1)
    l1_minute.on_last("cris", 1.59, m + 59, size=980, cum_volume=34_853_980)
    l1_minute.on_last("cris", 1.59, m + 60, size=100, cum_volume=34_854_080)  # 07:21 opens: 07:20 rolls
    _drain()

    first = _bars("CRIS")[0]
    assert first["t"] == "2026-11-04T12:20:00Z"
    assert _ohlcv(first) == (1.43, 1.60, 1.43, 1.59, 100 + 34_853_980 - 33_399_831)


def test_a_written_minute_is_not_written_again_until_it_changes(store, monkeypatch):
    writes: list[float] = []
    monkeypatch.setattr(l1_minute, "enqueue_intraday_bar", lambda **kw: writes.append(kw["volume"]))
    m = at("2026-11-04", 9, 31)
    l1_minute.on_last("abcd", 4.00, m + 5, size=100, cum_volume=1_000)
    for k in range(10):
        l1_minute.flush_elapsed(m + 60 + k * FLUSH_EVERY)
    assert writes == [100.0]
    l1_minute.on_last("abcd", 4.01, m + 59, size=50, cum_volume=1_050)
    l1_minute.flush_elapsed(m + 64)
    l1_minute.flush_elapsed(m + 65)
    assert writes == [100.0, 150.0]


def test_listeners_hear_a_minute_once_and_a_late_last_reads_its_real_open(store):
    heard: list[tuple[str, dict]] = []

    def listener(kind: str, _sym: str, payload: dict) -> None:
        heard.append((kind, payload))

    l1_minute.add_listener(listener)
    try:
        m = at("2026-11-04", 9, 31)
        l1_minute.on_last("abcd", 4.00, m + 5, size=100, cum_volume=1_000)
        l1_minute.on_last("abcd", 4.20, m + 40, size=100, cum_volume=1_100)
        l1_minute.flush_elapsed(m + 60.1)
        l1_minute.on_last("abcd", 4.10, m + 59, size=100, cum_volume=1_200)   # after the minute was heard
        l1_minute.flush_elapsed(m + 60.5)
    finally:
        l1_minute.remove_listener(listener)
    bars = [p for kind, p in heard if kind == "bar"]
    lasts = [p for kind, p in heard if kind == "last"]
    assert len(bars) == 1                                  # the setup scanner keeps the first one anyway
    assert (bars[0]["o"], bars[0]["c"], bars[0]["v"]) == (4.00, 4.20, 200.0)
    assert [p["bar_open"] for p in lasts] == [4.00, 4.00, 4.00]   # it used to read 4.10, the late price


def test_an_update_stamped_before_the_newest_minute_counts_its_shares_there(store):
    """IBKR's second went backwards (a line asked again): the closed candle is never reopened, and
    the shares, which did trade, are not lost."""
    m = at("2026-11-04", 10, 0)
    l1_minute.on_last("abcd", 4.00, m + 10, size=100, cum_volume=10_000)
    l1_minute.on_last("abcd", 4.10, m + 70, size=200, cum_volume=10_200)      # 10:01 opens: 10:00 written
    l1_minute.on_last("abcd", 9.99, m + 30, size=300, cum_volume=10_500)      # stamped 10:00:30
    l1_minute.flush_elapsed(m + 125)
    _drain()

    bars = _bars("ABCD")
    assert [_ohlcv(b) for b in bars] == [
        (4.00, 4.00, 4.00, 4.00, 100),       # no 9.99 wick on a closed candle
        (4.10, 4.10, 4.10, 4.10, 500),       # 200 + its 300
    ]
    assert sum(b["v"] for b in bars) == 100 + (10_500 - 10_000)


def test_a_restarted_process_cannot_shrink_a_stored_minute(store):
    """A new process joins the minute late: its first update is a baseline, so its count is smaller."""
    m = at("2026-11-04", 9, 45)
    l1_minute.on_last("abcd", 5.00, m + 1, size=100, cum_volume=1_000_000)
    l1_minute.on_last("abcd", 5.10, m + 20, size=100, cum_volume=1_049_900)
    l1_minute.flush_elapsed(m + 60.1)
    _drain()
    l1_minute.reset_for_tests()                                               # the backend restarts
    l1_minute.on_last("abcd", 5.05, m + 40, size=100, cum_volume=1_060_000)
    l1_minute.on_last("abcd", 5.20, m + 55, size=100, cum_volume=1_080_000)
    l1_minute.flush_elapsed(m + 60.5)
    _drain()

    assert _ohlcv(_bars("ABCD")[0]) == (5.00, 5.20, 5.00, 5.20, 50_000)


def test_yesterdays_last_minute_is_let_go_at_midnight(store):
    """IBKR repeats a line's last trade on the new day's first update. Held overnight, yesterday's
    19:59 would have taken that trade's shares again."""
    m = at("2026-11-03", 19, 59)
    l1_minute.on_last("namm", 1.36, m + 10, size=100, cum_volume=27_000_000)
    l1_minute.on_last("namm", 1.36, m + 49, size=400, cum_volume=27_005_000)
    l1_minute.flush_elapsed(m + 60.2)
    l1_minute.flush_elapsed(at("2026-11-04", 0, 0, 0.3))
    assert l1_minute._open == {}
    # 04:00:05: the day high resets, and the update carries yesterday's last trade and second
    l1_minute.on_last("namm", 1.36, m + 49, size=400, cum_volume=0)
    l1_minute.on_last("namm", 1.32, at("2026-11-04", 4, 0, 6), size=300, cum_volume=300)
    l1_minute.flush_elapsed(at("2026-11-04", 4, 2))
    _drain()

    bars = _bars("NAMM")
    assert [(b["t"], b["v"]) for b in bars] == [
        ("2026-11-04T00:59:00Z", 5_100),     # unchanged
        ("2026-11-04T09:00:00Z", 300),
    ]


# -- a second counter on the line --------------------------------------------------------------------


def _minute_volume(updates: list[tuple[float, float, float]]) -> float:
    """Feed ``(seconds into 2026-11-04 19:59, price, day volume)`` and read back that minute's volume."""
    m = at("2026-11-04", 19, 59)
    for ss, price, day_volume in updates:
        l1_minute.on_last("abcd", price, m + ss, size=100, cum_volume=day_volume)
    l1_minute.flush_elapsed(m + 61)
    _drain()
    return _bars("ABCD")[0]["v"]


def test_a_second_counter_on_the_line_adds_nothing(store):
    """XLAB 2026-10-16 19:59:58: IBKR's RTVolume total (the tape's own 171,624,612) and a counter 3% under it
    took turns on one line. Each return to the real total counted 5,285,464 shares again."""
    assert _minute_volume([
        (1, 2.14, 171_624_000), (58, 2.14, 171_624_609), (58, 2.14, 171_624_612),
        (58, 2.14, 166_339_148), (58, 2.14, 171_624_612), (58, 2.14, 166_339_148),
    ]) == 100 + 612


def test_a_stale_total_then_the_real_one_adds_nothing(store):
    """FRGT 2026-10-06 19:48:20: 331,702,034, then a stale 145,465,583, then 331,799,053 -- 186M shares
    no one traded, on a 220M-share day."""
    assert _minute_volume([
        (1, 0.288, 331_702_033), (20, 0.2849, 145_465_583), (20, 0.2849, 331_799_053), (29, 0.284, 331_802_291),
    ]) == 100 + 331_802_291 - 331_702_033


def test_a_scaled_total_is_no_volume(store):
    """GRAL 2026-09-21: the line read 2,106,490, then 2,071,000,800,607 in the same second."""
    assert _minute_volume([
        (1, 108.27, 2_106_490), (1, 108.27, 2_071_000_800_607), (30, 108.30, 2_106_590), (40, 108.2, 2_082_703_005_463),
        (50, 108.21, 2_106_690),
    ]) == 100 + 200


def test_a_new_session_starts_its_own_count_with_no_last_between(store):
    """No overnight last dropped yesterday's baseline: today's lower total is a new day, not a second counter."""
    l1_minute.on_last("abcd", 1.36, at("2026-11-03", 19, 59, 49), size=100, cum_volume=27_206_968)
    l1_minute.on_last("abcd", 1.32, at("2026-11-04", 4, 0, 5), size=300, cum_volume=40_000)
    l1_minute.on_last("abcd", 1.33, at("2026-11-04", 4, 0, 20), size=100, cum_volume=40_100)
    l1_minute.flush_elapsed(at("2026-11-04", 4, 2))
    _drain()
    assert [b["v"] for b in _bars("ABCD")] == [100, 400]      # 300 (a baseline) + 100


# -- the store ---------------------------------------------------------------------------------------


def test_a_smaller_live_write_never_lowers_a_stored_minute(store):
    ts = at("2026-11-04", 9, 50)

    def write(**kw):
        bar = {"symbol": "ABCD", "ts": ts, "open_": 5.0, "high": 5.0, "low": 5.0, "close": 5.0,
               "volume": 0.0, "timeframe": "1Min", **kw}
        wq.enqueue_intraday_bar(**bar)
        _drain()
        return _ohlcv(_bars("ABCD")[0])

    assert write(volume=50_000.0, high=5.2) == (5.0, 5.2, 5.0, 5.0, 50_000)
    assert write(volume=20_000.0, low=4.9, close=5.1) == (5.0, 5.2, 4.9, 5.1, 50_000)
    assert write(volume=60_000.0, close=5.15) == (5.0, 5.2, 4.9, 5.15, 60_000)
    assert write(volume=0.0) == (5.0, 5.2, 4.9, 5.0, 60_000)


def test_a_live_write_still_never_touches_a_hist_minute(store):
    ts = at("2026-11-04", 9, 50)
    hist = {"t": ts, "o": 1.20, "h": 1.40, "l": 1.10, "c": 1.35, "v": 2_938}
    bars_store.write_payload({"symbol": "ABCD", "timeframe": "1Min", "bars": [hist],
                              "coverage": bars_store.coverage_from_bars([hist], filling=False)})
    l1_minute.on_last("abcd", 9.99, ts + 5, size=100, cum_volume=1_000)
    l1_minute.on_last("abcd", 9.99, ts + 30, size=100, cum_volume=90_000)
    l1_minute.flush_elapsed(ts + 61)
    _drain()
    assert _ohlcv(_bars("ABCD")[0]) == (1.20, 1.40, 1.10, 1.35, 2_938)


# -- every share, on any arrival order the desk sees -------------------------------------------------


def _stream(rng: random.Random, start: float, minutes: int, *, noisy: bool = False) -> list[tuple]:
    """IBKR-like L1 updates as ``(arrival, stamp, price, size, day_volume, real)``.

    A trade's stamp is its whole second (tick 45). Arrival trails it as on the desk on 2026-11-04 --
    mostly well under 2 s, now and then 4 s, rarely 13 s -- and IBKR delivers updates in order, so
    arrival never runs ahead of a later update's. The day volume grows by every trade; some updates
    move only the price (no growth) or only the volume. ``noisy`` lines also carry what the census of
    19,984 streamed symbol-days found: a second counter a few percent under the real one, a stale
    earlier total, and now and then a 10^6-scaled one (``real`` False: no share of them traded).
    """
    out = []
    trade = start + rng.uniform(0, 3)
    arrival = trade
    day_volume = float(rng.randint(100_000, 50_000_000))
    totals = [day_volume]
    gap_mean = rng.choice([0.1, 0.3, 1.0, 5.0])
    while trade < start + minutes * 60:
        size = float(rng.choice([0, 100, 100, 200, 300, 500, rng.randint(1, 99), rng.randint(100, 25_000)]))
        day_volume += size
        totals.append(day_volume)
        roll = rng.random()
        lag = rng.uniform(0.05, 1.8) if roll < 0.9 else rng.uniform(1.8, 4.0) if roll < 0.98 else rng.uniform(4, 13)
        arrival = max(arrival + 0.001, trade + lag)
        price = round(rng.uniform(1.0, 2.0), 4)
        out.append((arrival, float(int(trade)), price, size, day_volume, True))
        if noisy and rng.random() < 0.06:
            kind = rng.random()
            other = (day_volume * rng.uniform(0.95, 0.99) if kind < 0.5 else rng.choice(totals) if kind < 0.9
                     else day_volume * 1e6)
            arrival += 0.001
            out.append((arrival, float(int(trade)), price, 0.0, other, False))
        trade += rng.expovariate(1.0 / gap_mean)
    return out


def _expected(updates) -> dict[float, list[float]]:
    """Each minute's candle and volume, straight from the stream: its real counter's growth (baseline rule
    included); the other figures' updates move the candle, never the volume."""
    minutes: dict[float, list[float]] = {}
    prior = None
    for _arrival, stamp, price, size, day_volume, real in updates:
        inc = 0.0 if not real else size if prior is None else day_volume - prior
        prior = day_volume if real else prior
        minute = float(int(stamp // 60) * 60)
        bar = minutes.get(minute)
        if bar is None:
            minutes[minute] = [price, price, price, price, inc]
        else:
            bar[1], bar[2], bar[3] = max(bar[1], price), min(bar[2], price), price
            bar[4] += inc
    return minutes


def _replay(updates, end: float) -> None:
    """Deliver the stream on its arrival clock, with the flush loop ticking every FLUSH_EVERY between."""
    clock = updates[0][0] if updates else end
    for arrival, stamp, price, size, day_volume, _real in updates:
        while clock + FLUSH_EVERY <= arrival:
            clock += FLUSH_EVERY
            l1_minute.flush_elapsed(clock)
        l1_minute.on_last("rand", price, stamp, size=size, cum_volume=day_volume)
    while clock < end:
        clock += FLUSH_EVERY
        l1_minute.flush_elapsed(clock)


def _check_every_share(seed: int, monkeypatch, *, noisy: bool) -> None:
    l1_minute.reset_for_tests()
    writes: dict[float, list[tuple]] = {}
    heard: list[float] = []
    monkeypatch.setattr(l1_minute, "enqueue_intraday_bar", lambda **kw: writes.setdefault(kw["ts"], []).append(
        (kw["open_"], kw["high"], kw["low"], kw["close"], kw["volume"])))
    monkeypatch.setattr(l1_minute, "_listeners", [lambda kind, _s, p: heard.append(p["t"]) if kind == "bar" else None])
    rng = random.Random(seed)
    start = at("2026-11-04", 9, 30)
    updates = _stream(rng, start, minutes=rng.choice([2, 4, 8]), noisy=noisy)
    _replay(updates, end=updates[-1][0] + 120)
    expected = _expected(updates)

    assert sorted(writes) == sorted(expected)
    for minute, bar in expected.items():
        assert writes[minute][-1] == pytest.approx(tuple(bar)), f"seed {seed} minute {minute}"
        vols = [w[4] for w in writes[minute]]
        assert vols == sorted(vols), f"seed {seed}: a write lowered minute {minute}: {vols}"
    assert heard == sorted(expected)                                   # each minute heard once, in order
    real = [u for u in updates if u[5]]
    assert sum(w[-1][4] for w in writes.values()) == pytest.approx(real[0][3] + real[-1][4] - real[0][4])
    l1_minute.reset_for_tests()


@pytest.mark.parametrize("seed", range(300))
def test_every_share_lands_once_in_its_own_minute(seed, monkeypatch):
    _check_every_share(seed, monkeypatch, noisy=False)


@pytest.mark.parametrize("seed", range(300))
def test_a_second_counter_or_a_stale_total_never_adds_a_share(seed, monkeypatch):
    """The same streams with the census's other figures mixed in: each minute still holds its real growth."""
    _check_every_share(seed, monkeypatch, noisy=True)


def test_the_random_streams_reach_the_late_path():
    """Guard for the test above: its streams do deliver updates after their minute was written."""
    late = 0
    for seed in range(300):
        rng = random.Random(seed)
        start = at("2026-11-04", 9, 30)
        updates = _stream(rng, start, minutes=rng.choice([2, 4, 8]))
        late += sum(1 for arrival, stamp, *_ in updates if arrival >= (int(stamp // 60) + 1) * 60 + FLUSH_EVERY)
    assert late > 1_000


@pytest.mark.parametrize("seed", range(12))
def test_every_share_reaches_the_chart(seed, store):
    """The same streams end to end: the write queue and the chart's store read."""
    rng = random.Random(1_000 + seed)
    start = at("2026-11-04", 9, 30)
    updates = _stream(rng, start, minutes=6)
    _replay(updates, end=updates[-1][0] + 120)
    _drain()
    expected = _expected(updates)
    got = {bar_unix(b): _ohlcv(b) for b in _bars("RAND")}
    assert sorted(got) == sorted(expected)
    for minute, bar in expected.items():
        o, h, low, c, v = bar
        assert got[minute] == pytest.approx((o, h, low, c, int(v))), f"seed {seed} minute {minute}"
