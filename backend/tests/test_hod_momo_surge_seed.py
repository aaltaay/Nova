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


def test_count_surge_none_skips_short_live_warmup_span():
    """Live-only buffers are structurally not-ready until the squeeze window
    has two prices -- that is warmup, not a Nova defect."""
    from collections import deque

    from hod_momo_flow import count_surge_none_after_seed

    now = time.time()
    short = deque([(now - 30.0, 1.0), (now, 1.1)])
    # Two prints 400s apart: span looks long, but the last 5 min has one print.
    gapped = deque([(now - 400.0, 1.0), (now, 1.1)])
    dense = deque([
        (now - 400.0, 1.0),
        (now - 240.0, 1.0),
        (now - 120.0, 1.05),
        (now, 1.1),
    ])
    bad = count_surge_none_after_seed(
        seeded={"SHORT", "GAPPED", "DENSE", "EMPTY"},
        price_buffer={"SHORT": short, "GAPPED": gapped, "DENSE": dense},
        ticker_snaps={},
        surge_fn=lambda *_a, **_k: None,
        window_min=5,
    )
    # SHORT has 2 prices 30s apart -- that IS a populated squeeze window.
    assert bad == 2  # SHORT + DENSE; GAPPED has one print in the last 5 min


def test_stale_store_plus_fresh_tick_is_not_surge_none():
    """Afterhours: RTH 1Min fossils + one live print must not trip integrity.

    price_surge looks at the last 5 min of the latest print. Old bars are
    outside that window, so Squeeze is honestly not computable -- not a
    failed seed.
    """
    from collections import deque

    from hod_momo_flow import count_surge_none_after_seed
    from hod_momo_filters import price_surge

    now = time.time()
    buf = deque([
        (now - 7200.0, 5.00),
        (now - 7140.0, 5.10),
        (now - 7080.0, 5.20),
        (now, 4.00),
    ])
    assert price_surge(buf, 5, "low_to_current") is None
    bad = count_surge_none_after_seed(
        seeded={"CAST"},
        price_buffer={"CAST": buf},
        ticker_snaps={},
        surge_fn=price_surge,
        window_min=5,
    )
    assert bad == 0


def test_seed_symbol_store_hit_seeds_high_and_buffer(monkeypatch):
    from hod_momo_surge_seed import seed_symbol
    import hod_momo_high as high

    state = hm.replace_state(HodMomoState())
    now = datetime.now(timezone.utc)
    bars = []
    for i in range(20):
        t = now.timestamp() - (20 - i) * 60
        iso = datetime.fromtimestamp(t, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        bars.append({
            "t": iso, "o": 4.0, "h": 5.0 + i * 0.01, "l": 3.8, "c": 4.2, "v": 1000,
        })

    monkeypatch.setattr(
        "bars_store.read",
        lambda *_a, **_k: {"bars": bars, "coverage": {"filling": False}},
    )

    kind = seed_symbol("SEED", "ibkr")
    assert kind == "store"
    assert "SEED" in state.surge_seeded
    assert high.is_high_seeded("SEED")
    assert len(state.price_buffer.get("SEED") or []) >= 2


def test_seed_symbol_store_miss_marks_attempted_live(monkeypatch):
    from hod_momo_surge_seed import seed_symbol

    state = hm.replace_state(HodMomoState())
    monkeypatch.setattr("bars_store.read", lambda *_a, **_k: None)
    kind = seed_symbol("MISS", "ibkr")
    assert kind == "live"
    assert "MISS" in state.surge_seeded
    assert not (state.price_buffer.get("MISS") or [])


def test_seed_symbol_never_calls_request_bars(monkeypatch):
    import inspect

    import hod_momo_surge_seed as seed_mod
    from hod_momo_surge_seed import seed_symbol

    src = inspect.getsource(seed_mod)
    assert "historical_service" not in src
    assert "request_bars" not in src

    hm.replace_state(HodMomoState())

    def boom(*_a, **_k):
        raise AssertionError("HOD must not call historical_service.request_bars")

    monkeypatch.setattr("ibkr.historical_service.request_bars", boom)
    monkeypatch.setattr("bars_store.read", lambda *_a, **_k: None)
    assert seed_symbol("NOIB", "ibkr") == "live"


def test_seed_symbol_stale_store_does_not_poison_surge_buffer(monkeypatch):
    """Chart 1Min last bar 90 min ago must not become the live Squeeze path."""
    from hod_momo_surge_seed import seed_symbol
    import hod_momo_high as high
    from hod_momo_filters import price_surge

    # Pin midday ET. Wall-clock near 04:00 ET drops 90-minute-old bars as the
    # prior session, so is_high_seeded is false even though the store is "today."
    fixed_now = datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(time, "time", lambda: fixed_now.timestamp())
    monkeypatch.setattr(
        "hod_momo_surge_seed.session_key_et",
        lambda now=None: session_key_et(fixed_now),
    )

    state = hm.replace_state(HodMomoState())
    now = fixed_now
    bars = []
    for i in range(20):
        t = now.timestamp() - 90 * 60 - (20 - i) * 60
        iso = datetime.fromtimestamp(t, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        bars.append({
            "t": iso, "o": 4.0, "h": 9.5, "l": 3.8, "c": 4.2, "v": 1000,
        })
    monkeypatch.setattr(
        "bars_store.read",
        lambda *_a, **_k: {"bars": bars, "coverage": {"filling": False}},
    )
    kind = seed_symbol("STALE", "ibkr")
    assert high.is_high_seeded("STALE")
    assert state.session_highs["STALE"] == 9.5
    buf = state.price_buffer.get("STALE") or []
    assert len(buf) == 0
    assert kind == "live"
    hm._update_price_buffer("STALE", 4.0, time.time())
    assert price_surge(state.price_buffer["STALE"], 5, "low_to_current") is None
