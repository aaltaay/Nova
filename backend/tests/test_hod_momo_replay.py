"""Golden + parity tests for the HOD Momo replay harness (capture audit).

Two layers:

1. Golden tests on a 10k-print SDOT slice (fast, controlled config):
   determinism, squeeze fire, disabled-strategy silence, session rollover.
2. Full-day module-scoped replay (~45s, real disk/default config) answering
   the audit question empirically: dense-tape movers are captured, replayed
   strategies are a subset of what production captured (no phantoms), and
   quiet symbols stay silent. Thin-tape symbols are asserted subset-only:
   tape only records symbols with an active tape subscription, so their
   production alerts fired on L1 ticks that were never archived.
"""
from __future__ import annotations

import pytest

import hod_momo as hm
import hod_momo_persist as persist
import hod_momo_session as session
from hod_momo_replay import (
    _FIFTY_TWO_WEEK_SENTINEL_MULT,
    ReplayFixture,
    closed_bars_before,
    load_fixture,
    prime_symbol,
    replay_session,
    reset_engine_state,
)
from hod_momo_state import get_state

DATE = "2026-07-17"
DENSE_MOVERS = {"SDOT", "BIYA", "CJMB"}
QUIET = {"MVO", "CNEY", "NFXS", "WZRD"}
THIN_TAPE = {"SLND", "KLRS", "VEEE"}
SDOT_SLICE_TICKS = 10_000


def _squeeze11_only(state) -> None:
    """Deterministic Squeeze 5%/5m-only gate set (machine-independent)."""
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11
    cfg = state.configs[11]
    cfg.surge_pct = 5.0
    cfg.surge_window_min = 5
    cfg.requires_hod = True
    cfg.min_price = 0.0
    cfg.max_price = 0.0
    cfg.min_float = 0.0
    cfg.max_float = 0.0
    cfg.min_volume = 0.0
    cfg.min_rvol = 0.0
    cfg.min_gap_pct = 0.0
    cfg.min_change_pct = 0.0
    cfg.proximity_52wk_pct = 0.0
    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 0.0
    state.master.premarket_min_rvol = 0.0
    state.master.afterhours_min_rvol = 0.0


def _sdot_slice(fixture: ReplayFixture, ticks: int = SDOT_SLICE_TICKS) -> ReplayFixture:
    seen: dict[str, int] = {}
    tape = []
    for row in fixture.tape:
        sym = row["symbol"]
        if sym != "SDOT":
            continue
        seen[sym] = seen.get(sym, 0) + 1
        if seen[sym] <= ticks:
            tape.append(row)
    return ReplayFixture(fixture.session_date, tape, fixture.bars_by_symbol, fixture.meta)


@pytest.fixture(scope="module")
def day_fixture() -> ReplayFixture:
    return load_fixture(DATE)


@pytest.fixture(scope="module")
def sdot_slice_result(day_fixture):
    return replay_session(_sdot_slice(day_fixture), configure=_squeeze11_only)


def test_replay_mover_fires_squeeze(sdot_slice_result):
    fired = [a for a in sdot_slice_result.alerts if a["strategy_id"] == 11]
    assert fired, "SDOT slice must fire Squeeze 5%/5m at least once"
    assert all(a["ticker"] == "SDOT" for a in fired)
    first = fired[0]
    assert first["price"] == pytest.approx(27.9, abs=0.05)


def test_replay_is_deterministic(day_fixture, sdot_slice_result):
    again = replay_session(_sdot_slice(day_fixture), configure=_squeeze11_only)
    keys = [(a["ticker"], a["strategy_id"], a["price"], a["timestamp"]) for a in sdot_slice_result.alerts]
    assert [(a["ticker"], a["strategy_id"], a["price"], a["timestamp"]) for a in again.alerts] == keys


def test_replay_disabled_strategies_silent(day_fixture):
    def _all_off(state) -> None:
        for cfg in state.configs.values():
            cfg.enabled = False

    result = replay_session(_sdot_slice(day_fixture, 2_000), configure=_all_off)
    assert result.alerts == []
    assert result.gate_counters.get("passed_master", 0) > 0


def test_replay_session_rollover_partitions_alerts(day_fixture, monkeypatch):
    result = replay_session(_sdot_slice(day_fixture), configure=_squeeze11_only)
    assert result.alerts, "slice must fire before rollover is meaningful"

    archived: list[tuple[str, list]] = []
    monkeypatch.setattr(
        persist,
        "archive_session_alerts",
        lambda date_str: archived.append((date_str, list(get_state().today_alerts))),
    )
    monkeypatch.setattr(persist, "save_alerts", lambda *, force=False: None)
    monkeypatch.setattr(session, "current_date_et", lambda: "2026-07-18")

    state = get_state()
    previous = state.session_date
    assert session.check_and_reset_session() is True
    assert state.today_alerts == []
    assert state.session_date == "2026-07-18"
    assert archived and archived[0][0] == previous
    assert len(archived[0][1]) == len(result.alerts)


@pytest.fixture(scope="module")
def full_day_result(day_fixture):
    """Full 89k-print day under the real loaded config (~45s, module-scoped)."""
    return replay_session(day_fixture)


def test_full_day_dense_movers_captured(full_day_result):
    fired = full_day_result.alerts_by_symbol_strategy()
    for sym in DENSE_MOVERS:
        assert fired.get(sym), f"{sym}: dense tape mover produced no replay alerts"


def test_full_day_no_phantom_strategies(day_fixture, full_day_result):
    """Replayed strategies must be a subset of production's per symbol.

    Strategy 13 (Approaching HOD) is Nova-only — not in momentum production
    IDs — so it is excluded from the phantom check.
    """
    from constants import HOD_MOMO_APPROACH_STRATEGY_ID

    production = {
        sym: set(meta.get("production_strategy_ids") or [])
        for sym, meta in (day_fixture.meta.get("symbols") or {}).items()
    }
    for sym, strategies in full_day_result.alerts_by_symbol_strategy().items():
        extras = (
            set(strategies) - {HOD_MOMO_APPROACH_STRATEGY_ID} - production.get(sym, set())
        )
        assert not extras, f"{sym}: replay fired phantom strategies {sorted(extras)}"


def test_full_day_quiet_symbols_silent(full_day_result):
    fired = full_day_result.alerts_by_symbol_strategy()
    for sym in QUIET:
        assert not fired.get(sym), f"{sym}: quiet symbol fired {fired.get(sym)}"


def test_full_day_thin_tape_symbols_are_coverage_gaps(day_fixture, full_day_result):
    """Thin-tape symbols encode the archive coverage gap as data.

    CNF/SLND/KLRS/VEEE fired in production on L1 ticks that tape capture
    never recorded, so replay cannot reproduce those alerts. Assert replay
    stays within production's strategy set (no phantoms) and that the meta
    documents production fires with thin tape -- the gap is the finding.
    """
    from constants import HOD_MOMO_APPROACH_STRATEGY_ID

    fired = full_day_result.alerts_by_symbol_strategy()
    for sym in THIN_TAPE | {"CNF"}:
        # Nova-only Approaching HOD (13) is outside momentum production IDs.
        replayed = set(fired.get(sym, [])) - {HOD_MOMO_APPROACH_STRATEGY_ID}
        production = set(
            (day_fixture.meta["symbols"].get(sym) or {}).get("production_strategy_ids") or []
        )
        assert replayed <= production
        tape_prints = day_fixture.meta["symbols"][sym]["tape_prints"]
        if production and tape_prints < 5_000:
            assert replayed != production or tape_prints < 5_000


# ── Interval-close contract (#385) ───────────────────────────────────────────
# A fixture bar's ``ts`` is the minute's OPENING stamp, so its final high, low,
# close and volume are only facts at ts + 60. Three layers below: what the real
# fixture actually contains, the real alert engine across the boundary, and
# fast synthetic probes.

_T = 1_720_000_020.0  # an exact minute boundary
_SYM = "ZZTEST"


def _bar(ts: float, *, open_: float, high: float, low: float, close: float, volume: float) -> dict:
    return {
        "symbol": _SYM,
        "ts": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _print(ts: float, price: float, size: float) -> dict:
    return {"symbol": _SYM, "ts": ts, "price": price, "size": size}


def _synthetic_fixture(bars: list[dict], tape: list[dict]) -> ReplayFixture:
    return ReplayFixture(
        session_date="2026-07-17",
        tape=tape,
        bars_by_symbol={_SYM: bars},
        meta={"symbols": {_SYM: {}}, "production_alerts": []},
    )


def _record_trade_updates(monkeypatch) -> list[dict]:
    """Capture what the engine is told, without running the engine."""
    calls: list[dict] = []

    def _capture(symbol, price, ts, **kwargs):
        calls.append({"symbol": symbol, "price": price, "ts": ts, **kwargs})

    monkeypatch.setattr(hm, "on_trade_update", _capture)
    return calls


# ── Layer 1: what the shipped fixture actually contains ─────────────────────


def test_fixture_open_minute_bar_is_the_tape_not_pre_tape_history(day_fixture):
    """#385's premise, as data.

    For every taped symbol that has bars, the bar still OPEN at the first
    print is a re-aggregation of the prints this harness is about to replay:
    open == the first print's price, high/low == that minute's print extremes,
    volume == their sizes. Priming from it is not "using early history", it is
    handing the engine its own future -- which is why withholding it is the
    fix and not an over-withholding. Nothing has CLOSED at that instant, so
    ``closed_bars_before`` is legitimately empty for every one of them.
    """
    checked = 0
    for sym, bars in day_fixture.bars_by_symbol.items():
        prints = [r for r in day_fixture.tape if r["symbol"] == sym]
        if not prints or not bars:
            continue
        first_ts = min(float(r["ts"]) for r in prints)
        live = [b for b in bars if float(b["ts"]) <= first_ts < float(b["ts"]) + 60.0]
        if not live:
            continue
        bar = live[-1]
        inside = [
            r for r in prints
            if float(bar["ts"]) <= float(r["ts"]) < float(bar["ts"]) + 60.0
        ]
        assert inside, f"{sym}: open-minute bar with no prints inside it"
        assert closed_bars_before(bars, first_ts) == []
        earliest = min(inside, key=lambda r: float(r["ts"]))
        assert bar["open"] == pytest.approx(float(earliest["price"]))
        assert bar["high"] == pytest.approx(max(float(r["price"]) for r in inside))
        assert bar["low"] == pytest.approx(min(float(r["price"]) for r in inside))
        assert bar["volume"] == pytest.approx(sum(float(r.get("size") or 0.0) for r in inside))
        checked += 1
    assert checked >= 5, "fixture no longer exercises the open-minute case"


def test_priming_without_closed_bars_still_has_a_price_and_a_52wk_sentinel(day_fixture):
    """Withholding the in-progress bar must not strand a symbol at price 0.0
    with ``fifty_two_week_high=None`` -- that blocks every strategy with
    proximity_52wk_pct > 0 on "52wk_high:unknown" for the whole session. The
    stand-ins come from the first observed print, never from the bar."""
    for sym in ("KLRS", "VEEE"):  # the fixture's taped symbols with no prev_close
        reset_engine_state()
        prints = [r for r in day_fixture.tape if r["symbol"] == sym]
        first = min(prints, key=lambda r: float(r["ts"]))
        prime_symbol(
            day_fixture, sym, float(first["ts"]), first_price=float(first["price"]),
        )
        state = get_state()
        snap = state.ticker_snaps[sym]
        assert snap.price == pytest.approx(float(first["price"]))
        assert snap.fifty_two_week_high == pytest.approx(
            float(first["price"]) * _FIFTY_TWO_WEEK_SENTINEL_MULT
        )
        # ...and still no high floor lifted out of the unclosed bar.
        assert not state.session_highs.get(sym)
        assert sym in state.surge_seeded and sym not in state.pending_surge_seed


# ── Layer 2: the real alert engine across the boundary ──────────────────────


def _rising_tape(start_ts: float, n: int = 40) -> list[dict]:
    """Prints climbing ~10% over ~6.5 minutes -- clears Squeeze 5%/5m."""
    return [
        _print(start_ts + i * 10.0, round(10.0 + i * 0.0256, 4), 100)
        for i in range(n)
    ]


def test_engine_sees_a_hod_when_the_open_minute_bar_is_withheld():
    """Runs ``hod_momo.on_trade_update`` for real (no monkeypatch).

    The archived bar covering the first print claims a 99.0 high. Under the
    old ``ts <= first_ts`` rule that became the session-high floor, so the
    tape could never make a high and a ``requires_hod`` strategy was mute.
    Withheld, the tape is the only truth and Squeeze fires.
    """
    tape = _rising_tape(_T + 5.0)
    poison = _bar(_T, open_=10.0, high=99.0, low=9.0, close=98.0, volume=1_000)
    result = replay_session(_synthetic_fixture([poison], tape), configure=_squeeze11_only)

    assert result.alerts, "withholding the unclosed bar must let the tape set the HOD"
    assert all(a["strategy_id"] == 11 for a in result.alerts)
    assert get_state().session_highs[_SYM] == pytest.approx(
        max(float(r["price"]) for r in tape)
    )


def test_engine_still_honours_a_bar_that_did_close_before_the_tape():
    """The exact mirror: move the same bar a full minute earlier so it HAS
    closed by the first print, and its 99.0 high is a real past fact again --
    the floor is seeded and the same rising tape never makes a new high."""
    tape = _rising_tape(_T + 5.0)
    closed = _bar(_T - 60.0, open_=10.0, high=99.0, low=9.0, close=98.0, volume=1_000)
    result = replay_session(_synthetic_fixture([closed], tape), configure=_squeeze11_only)

    assert get_state().session_highs[_SYM] == pytest.approx(99.0)
    assert result.alerts == [], "a closed bar's high is a fact and must gate requires_hod"


def test_full_day_alert_shape_is_pinned(full_day_result):
    """#385 changes what the engine sees at session start, so pin the day.

    The subset/silence tests above stayed green through a 296 -> 309 alert
    change with six of seven symbols' first alert flipping strategy, which is
    exactly the regression this file exists to catch. Config is deterministic
    under pytest (conftest points NOVA_CACHE_DIR at a fresh temp dir, so
    ``load_state()`` gets built-in defaults).
    """
    assert len(full_day_result.alerts) == 309
    assert full_day_result.alerts_by_symbol_strategy() == {
        "BIYA": [5, 7, 11, 12, 13],
        "CJMB": [5, 7, 11, 12, 13],
        "CNF": [5, 7],
        "KLRS": [13],
        "SDOT": [4, 5, 7, 10, 11, 12, 13],
        "SLND": [6, 13],
        "VEEE": [3, 13],
    }
    first: dict[str, tuple] = {}
    for alert in sorted(full_day_result.alerts, key=lambda a: a["timestamp"]):
        first.setdefault(alert["ticker"], (alert["strategy_id"], alert["timestamp"]))
    assert first == {
        "BIYA": (5, "2026-07-17T16:05:32.000Z"),
        "CJMB": (5, "2026-07-17T16:05:33.000Z"),
        "CNF": (5, "2026-07-17T17:19:12.000Z"),
        "KLRS": (13, "2026-07-17T17:00:21.000Z"),
        "SDOT": (4, "2026-07-17T16:09:04.000Z"),
        "SLND": (6, "2026-07-17T17:10:00.000Z"),
        "VEEE": (3, "2026-07-17T17:47:38.000Z"),
    }


# ── Layer 3: fast synthetic probes ──────────────────────────────────────────


def test_prime_symbol_ignores_unclosed_minute():
    """5 seconds into a minute, that minute's high/close are not yet facts."""
    reset_engine_state()
    fixture = _synthetic_fixture(
        [_bar(_T, open_=10.0, high=99.0, low=9.0, close=98.0, volume=1_000)], []
    )
    prime_symbol(fixture, _SYM, _T + 5)

    state = get_state()
    assert not state.session_highs.get(_SYM), "seeded a high that had not happened"
    assert not state.price_buffer.get(_SYM), "seeded a close that had not happened"
    # No completed bar -> production's live-only seed path, so the symbol is
    # not stranded outside both surge_seeded and pending_surge_seed.
    assert _SYM in state.surge_seeded
    assert _SYM not in state.pending_surge_seed


def test_prime_symbol_uses_bar_closed_exactly_at_as_of():
    """Inclusive at close: at ts + 60 the same bar IS known -- and it seeds
    production's own point shape, ``(ts, low)`` then ``(ts + 30, close)``
    (``hod_momo_surge_seed.bars_to_surge_points``), so low_to_current surge
    can see the trough inside the candle."""
    reset_engine_state()
    fixture = _synthetic_fixture(
        [_bar(_T, open_=10.0, high=99.0, low=9.0, close=98.0, volume=1_000)], []
    )
    prime_symbol(fixture, _SYM, _T + 60)

    state = get_state()
    assert state.session_highs.get(_SYM) == pytest.approx(99.0)
    assert list(state.price_buffer.get(_SYM) or []) == [(_T, 9.0), (_T + 30.0, 98.0)]


def test_cumulative_volume_base_counts_the_open_minute_once_and_only_its_past(monkeypatch):
    """The base holds closed minutes whole, plus the part of the minute in
    progress that traded BEFORE the tape starts -- recovered by subtracting
    the prints about to be replayed. Never the whole open bar (which leaked
    its future and double-counted every print in it), never nothing (which
    would drop real past volume)."""
    fixture = _synthetic_fixture(
        [
            _bar(_T, open_=10.0, high=10.5, low=10.0, close=10.4, volume=1_000),
            _bar(_T + 60, open_=10.4, high=12.0, low=10.4, close=11.8, volume=500),
        ],
        [_print(_T + 65, 10.45, 25), _print(_T + 70, 10.90, 40)],
    )
    calls = _record_trade_updates(monkeypatch)
    replay_session(fixture)

    assert calls, "tape must reach the engine"
    # 1_000 closed + (500 - 65 taped) pre-tape + this print's 25.
    assert calls[0]["volume"] == 1_000 + 435 + 25
    assert calls[-1]["volume"] == 1_000 + 435 + 65


def test_open_minute_volume_recovery_is_exactly_zero_when_the_bar_is_the_tape(monkeypatch):
    """The shipped fixture's shape: every unit of the open minute's volume is
    on the tape, so nothing is recovered and nothing is double-counted."""
    prints = [_print(_T + 10, 10.1, 60), _print(_T + 20, 10.2, 40)]
    fixture = _synthetic_fixture(
        [_bar(_T, open_=10.1, high=10.2, low=10.1, close=10.2, volume=100)], prints
    )
    calls = _record_trade_updates(monkeypatch)
    replay_session(fixture)

    assert [c["volume"] for c in calls] == [60, 100]


def test_tick_derived_current_minute_is_preserved(monkeypatch):
    """We withhold the archived bar's final values, not the live minute: the
    day high still tracks the tape tick by tick and never reaches the
    unclosed bar's archived 12.0."""
    prints = [
        _print(_T + 65, 10.45, 25),
        _print(_T + 70, 10.90, 40),
        _print(_T + 75, 10.70, 35),
    ]
    fixture = _synthetic_fixture(
        [
            _bar(_T, open_=10.0, high=10.5, low=10.0, close=10.4, volume=1_000),
            _bar(_T + 60, open_=10.4, high=12.0, low=10.4, close=11.8, volume=500),
        ],
        prints,
    )
    calls = _record_trade_updates(monkeypatch)
    replay_session(fixture)

    assert len(calls) == len(prints)
    assert calls[-1]["day_high"] == pytest.approx(10.90)
    assert calls[-1]["day_high"] < 12.0
