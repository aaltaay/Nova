"""Exact surge parity, bounded history and ownership at real HOD session seams (#619)."""
from __future__ import annotations

import math
import random
import threading
from collections import deque
from types import SimpleNamespace

import pytest

import hod_momo_market as market
import hod_momo_state as state_mod
import hod_momo_trade as trade
import hod_momo_session as session
from tests.conftest import reset_hod_engine_state
from hod_momo_filters import price_surge
from hod_prices import PriceHistory


def _reference_add(buf, ts, price, cutoff):
    later = []
    while buf and buf[-1][0] > ts:
        later.append(buf.pop())
    buf.append((ts, price))
    buf.extend(reversed(later))
    while buf and buf[0][0] < cutoff:
        buf.popleft()


@pytest.mark.parametrize("method", ["low_to_current", "fixed_start", "unknown"])
def test_random_updates_match_plain_buffer_after_late_tied_and_expired_points(method):
    rng = random.Random(619)
    series, reference = PriceHistory(), deque()
    ts = 1_000_000.0
    for i in range(1800):
        ts += rng.choice((0, 0.1, 5, 30))
        point_ts = ts - rng.choice((0, 0, 0, 10, 120, 3900))
        price = rng.choice((0, -1, 1, 1, 2, 5, 10))
        series.add(point_ts, price, point_ts - 3600)
        _reference_add(reference, point_ts, price, point_ts - 3600)
        assert list(series) == list(reference)
        if i % 11 == 0:
            for window in (0, 1, 5, 7, 60, 120):
                assert price_surge(series, window, method) == price_surge(reference, window, method)


@pytest.mark.parametrize("prices", [[5, 4, 4, 6], [6, 5, 4, 3], [1, 1, 1, 1], [4, 0, 2, 3]])
def test_inclusive_boundary_duplicates_and_expiring_minimum(prices):
    points = list(zip((0.0, 300.0, 300.0, 600.0), prices, strict=True))
    history = PriceHistory(points)
    reference = deque(points)
    for method in ("fixed_start", "low_to_current"):
        assert price_surge(history, 5, method) == price_surge(reference, 5, method)
    history.add(600.001, 10, -3000)
    reference.append((600.001, 10))
    assert price_surge(history, 5, "low_to_current") == price_surge(reference, 5, "low_to_current")


@pytest.mark.parametrize("points", [[], [(0.0, 1.0)], [(0.0, math.nan), (1.0, 2.0)],
                                  [(0.0, 2.0), (1.0, math.nan)]])
def test_empty_insufficient_and_unknown_prices_keep_reference_meaning(points):
    for method in ("fixed_start", "low_to_current"):
        actual = price_surge(PriceHistory(points), 5, method)
        expected = price_surge(deque(points), 5, method)
        if expected is not None and math.isnan(expected):
            assert math.isnan(actual)
        else:
            assert actual == expected


def test_many_hours_do_not_retain_expired_arrays_or_index_leaves():
    history = PriceHistory()
    for ts in range(20_000):
        history.add(float(ts), 2.0 + ts % 7, ts - 3600)
        if ts % 1000 == 0:
            live = len(history)
            assert len(history._times) < max(1, 2 * live)
            assert len(history._tree) <= max(2, 8 * live)
    assert len(history) == 3601
    assert history[0] == (16399.0, 2.0 + 16399 % 7)
    history.trim_before(30_000)
    assert not history
    assert len(history._tree) == 2


def test_seeding_merges_prices_without_losing_live_order_or_creating_duplicates(hod_engine):
    market.update_price_buffer("ORDER", 4.0, 6000)
    market.update_price_buffer("ORDER", 5.0, 6030)
    assert market.seed_price_buffer("ORDER", [(6030, 5), (5900, 2), (6030, 4), (1000, 1)]) == 3
    assert list(hod_engine.price_buffer["ORDER"]) == [(5900, 2), (6000, 4), (6030, 5), (6030, 4)]
    assert market.seed_price_buffer("ORDER", [(6030, 5), (5900, 2)]) == 0


def test_live_trade_during_seed_normalization_survives_the_atomic_merge(hod_engine):
    market.update_price_buffer("RACE", 4.0, 6000)
    normalizing, trade_added = threading.Event(), threading.Event()
    results = []

    def stored_points():
        normalizing.set()
        assert trade_added.wait(5)
        yield 5900, 3.0
        yield 6010, 4.25

    def seed():
        results.append(market.seed_price_buffer("RACE", stored_points()))

    worker = threading.Thread(target=seed)
    worker.start()
    try:
        assert normalizing.wait(5)
        market.update_price_buffer("RACE", 5.0, 6030)
    finally:
        trade_added.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert results == [2]
    assert list(hod_engine.price_buffer["RACE"]) == [(5900, 3), (6000, 4), (6010, 4.25), (6030, 5)]


def test_current_state_replacement_discards_the_prior_sessions_index(hod_engine):
    market.update_price_buffer("DAY", 1.0, 1000)
    market.update_price_buffer("DAY", 10.0, 1300)
    assert price_surge(hod_engine.price_buffer["DAY"], 5, "low_to_current") == 900.0
    previous = hod_engine.price_buffer["DAY"]
    current = state_mod.replace_state()
    market.update_price_buffer("DAY", 50.0, 2000)
    assert current.price_buffer["DAY"] is not previous
    assert price_surge(current.price_buffer["DAY"], 5, "low_to_current") is None


def test_actual_session_rollover_discards_prices_before_the_next_evaluation(hod_engine, monkeypatch):
    hod_engine.session_date = "2026-10-13"
    market.update_price_buffer("DAY", 1.0, 1000)
    market.update_price_buffer("DAY", 10.0, 1300)
    monkeypatch.setattr(session, "current_date_et", lambda: "2026-10-14")
    assert session.check_and_reset_session()
    assert hod_engine.price_buffer == {}
    market.update_price_buffer("DAY", 50.0, 2000)
    assert price_surge(hod_engine.price_buffer["DAY"], 5, "low_to_current") is None


def test_route_reader_sees_a_complete_seed_while_writer_replaces_it():
    history = PriceHistory([(0, 1), (60, 2)])
    failures = []

    def read():
        for _ in range(2000):
            value = price_surge(history, 5, "low_to_current")
            if value not in (100.0, 200.0):
                failures.append(value)

    reader = threading.Thread(target=read)
    reader.start()
    try:
        for i in range(500):
            history.replace([(0, 1), (60, 2 if i % 2 else 3)])
    finally:
        reader.join(timeout=5)
    assert not reader.is_alive()
    assert failures == []


def test_real_engine_decisions_and_alerts_match_reference_history(monkeypatch):
    original_update = market.update_price_buffer
    outputs = []
    # Controlled venue-independent engine clock, without changing any gate.
    monkeypatch.setattr(trade, "time", SimpleNamespace(time=lambda: 10_000.0, monotonic=lambda: 10_000.0))
    for indexed in (False, True):
        reset_hod_engine_state()
        state = state_mod.get_state()
        state.master.min_rvol = state.master.min_volume = 0
        state.master.hod_required = False
        state.master.surge_pct = 1
        state.master.surge_window_min = 5
        for config in state.configs.values():
            config.enabled = config.strategy_id in (10, 11, 12)
            config.requires_hod = False
            config.min_rvol = 0

        def reference_update(symbol, price, ts, current_state=state):
            buf = current_state.price_buffer.setdefault(symbol, deque())
            _reference_add(buf, ts, price, ts - 3600)

        monkeypatch.setattr(market, "update_price_buffer", original_update if indexed else reference_update)
        for ts, price in ((9700, 10), (9740, 10.1), (9800, 10.6), (9800, 10.7),
                          (9900, 10.8), (9875, 10.3), (10000, 11.2), (10001, 10)):
            trade.on_trade_update("PARITY", price, ts, volume=100_000, day_high=12)
        outputs.append({
            "decisions": [(row.ts, row.price, row.gate_blocked, row.strategies, row.would_fire)
                          for row in state.recent_decisions],
            "alerts": [(alert.id, alert.strategy_id, alert.price, alert.momentum_pct)
                       for pending in state.pending_consolidation.values() for _, alert in pending],
            "counters": dict(state.gate_counters),
            "prices": list(state.price_buffer["PARITY"]),
        })
    assert outputs[0] == outputs[1]
    assert outputs[1]["alerts"], "the parity fixture must exercise firing, not only refusal"
