"""Tests for HOD Momo surge cold-start seeding (Warrior Squeeze parity)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import hod_momo as hm
from hod_momo_filters import price_surge
from hod_momo_surge_seed import bars_to_surge_points, filter_bars_to_session, parse_bar_ts
from hod_momo_state import HodMomoState
from market import session_key_et


def test_parse_bar_ts_iso_z():
    ts = parse_bar_ts("2026-07-15T19:05:00Z")
    expected = datetime(2026, 7, 15, 19, 5, 0, tzinfo=timezone.utc).timestamp()
    assert ts == expected


def test_bars_to_surge_points_uses_low_then_close():
    bars = [
        {"t": "2026-07-15T19:00:00Z", "o": 4.0, "h": 4.2, "l": 3.8, "c": 4.1, "v": 1000},
        {"t": "2026-07-15T19:01:00Z", "o": 4.1, "h": 4.5, "l": 4.0, "c": 4.4, "v": 2000},
    ]
    pts = bars_to_surge_points(bars)
    assert len(pts) == 4
    assert pts[0][1] == 3.8
    assert pts[1][1] == 4.1
    assert pts[1][0] == pts[0][0] + 30.0


def test_seed_price_buffer_enables_5pct_surge(monkeypatch):
    state = hm.replace_state(HodMomoState())

    sym = "HKIT"
    now = time.time()
    hm._update_price_buffer(sym, 4.09, now)
    assert price_surge(state.price_buffer[sym], 5, "low_to_current") is None

    bars = []
    for i in range(6):
        t = now - (6 - i) * 60
        low = 3.80
        close = 3.80 + i * 0.05
        bars.append({"t": t, "o": low, "h": close, "l": low, "c": close, "v": 10_000})
    points = bars_to_surge_points(bars)
    points.append((now, 4.09))
    n = hm.seed_price_buffer(sym, points)
    assert n >= 2
    surge = price_surge(state.price_buffer[sym], 5, "low_to_current")
    assert surge is not None
    assert surge >= 5.0


def test_filter_bars_to_session_drops_prior_session_sliver():
    """A `1 D` IBKR pull can include a bar from just before 04:00 ET on the
    prior calendar day — that stale bar must not pollute today's session-high
    seed (ADR 008 full-session HOD seed)."""
    # 2026-07-15 03:59 ET == 07:59 UTC — belongs to the 07-14 session (04:00
    # ET-anchored), not 07-15.
    prior_session_bar = {
        "t": "2026-07-15T07:59:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1,
    }
    # 2026-07-15 04:05 ET == 08:05 UTC — belongs to the 07-15 session.
    today_bar = {
        "t": "2026-07-15T08:05:00Z", "o": 2, "h": 9.99, "l": 2, "c": 2, "v": 1,
    }
    today_key = session_key_et(datetime(2026, 7, 15, 8, 5, tzinfo=timezone.utc))
    kept = filter_bars_to_session([prior_session_bar, today_bar], today_key)
    assert kept == [today_bar]


def test_request_surge_seed_is_once_per_symbol(monkeypatch):
    hm.replace_state(HodMomoState())
    hm.request_surge_seed("abc")
    hm.request_surge_seed("ABC")
    assert hm.pop_pending_surge_seeds(10) == ["ABC"]
    assert hm.pop_pending_surge_seeds(10) == []
    hm.mark_surge_seed_attempted("ABC")
    hm.request_surge_seed("ABC")
    assert hm.pop_pending_surge_seeds(10) == []
