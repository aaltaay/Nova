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
    ReplayFixture,
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


# ── Interval-close contract (#385) — fast synthetic layer ────────────────────
# A fixture bar's ``ts`` is the minute's OPENING stamp, so its final high,
# close and volume are only known at ts + 60. These pin that boundary without
# paying for the 45s full day.

_T = 1_720_000_020.0  # an exact minute boundary
_SYM = "ZZTEST"


def _bar(ts: float, *, open_: float, high: float, close: float, volume: float) -> dict:
    return {
        "symbol": _SYM,
        "ts": ts,
        "open": open_,
        "high": high,
        "low": min(open_, close),
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


def test_prime_symbol_ignores_unclosed_minute():
    """5 seconds into a minute, that minute's high/close are not yet facts."""
    reset_engine_state()
    fixture = _synthetic_fixture(
        [_bar(_T, open_=10.0, high=99.0, close=98.0, volume=1_000)], []
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
    """Inclusive at close: at ts + 60 the same bar IS known."""
    reset_engine_state()
    fixture = _synthetic_fixture(
        [_bar(_T, open_=10.0, high=99.0, close=98.0, volume=1_000)], []
    )
    prime_symbol(fixture, _SYM, _T + 60)

    state = get_state()
    assert state.session_highs.get(_SYM) == pytest.approx(99.0)
    assert list(state.price_buffer.get(_SYM) or []) == [(_T, 98.0)]


def test_cumulative_volume_base_excludes_unclosed_minute(monkeypatch):
    """The starting volume counts closed minutes only — and counts the
    in-progress minute once (via its prints), not twice."""
    fixture = _synthetic_fixture(
        [
            _bar(_T, open_=10.0, high=10.5, close=10.4, volume=1_000),
            _bar(_T + 60, open_=10.4, high=12.0, close=11.8, volume=500),
        ],
        [_print(_T + 65, 10.45, 25), _print(_T + 70, 10.90, 40)],
    )
    calls = _record_trade_updates(monkeypatch)
    replay_session(fixture)

    assert calls, "tape must reach the engine"
    assert calls[0]["volume"] == 1_000 + 25  # not 1_500 + 25


def test_tick_derived_current_minute_is_preserved(monkeypatch):
    """We withhold the archived bar, not the live minute: cumulative volume
    and the day high still track the tape tick by tick."""
    prints = [
        _print(_T + 65, 10.45, 25),
        _print(_T + 70, 10.90, 40),
        _print(_T + 75, 10.70, 35),
    ]
    fixture = _synthetic_fixture(
        [
            _bar(_T, open_=10.0, high=10.5, close=10.4, volume=1_000),
            _bar(_T + 60, open_=10.4, high=12.0, close=11.8, volume=500),
        ],
        prints,
    )
    calls = _record_trade_updates(monkeypatch)
    replay_session(fixture)

    assert len(calls) == len(prints)
    assert calls[-1]["volume"] == 1_000 + 25 + 40 + 35
    # Rises above the seeded floor (10.5) on a real print, and never reaches
    # the unclosed bar's archived 12.0 high.
    assert calls[-1]["day_high"] == pytest.approx(10.90)
