"""A weekend or holiday is no trading session (operator report, 2026-10-17).

On Saturday 2026-10-17 the scan loop ran in premarket mode from 04:00: the
session key rolled to the Saturday, Friday's frozen boards were cleared, and a
fresh Gainers roster -- every row IBKR's prior close, 0% and 0 volume -- was
marked live and saved over Friday's snapshot file.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import market
import scan_loop
from ibkr import scanner_session as ss
from runtime_state.state import TABLE_STATE_FROZEN, ScannerRuntimeState

ET = ZoneInfo("America/New_York")

FRIDAY = "2026-10-16"
SATURDAY = (2026, 10, 17)
SUNDAY = (2026, 10, 18)
MONDAY = (2026, 10, 19)
THANKSGIVING = (2026, 11, 26)


def _et(ymd, hh, mm=0):
    return datetime(*ymd, hh, mm, tzinfo=ET)


def _freeze_clock(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(market, "now_et", lambda: when)
    monkeypatch.setattr(ss, "now_et", lambda: when)
    monkeypatch.setattr(scan_loop, "_now_et", lambda: when)


@pytest.mark.parametrize("when, key", [
    (_et(SATURDAY, 4, 0), FRIDAY),
    (_et(SATURDAY, 10, 0), FRIDAY),
    (_et(SUNDAY, 23, 59), FRIDAY),
    (_et(MONDAY, 2, 0), FRIDAY),
    (_et(MONDAY, 4, 0), "2026-10-19"),
    (_et(THANKSGIVING, 10, 0), "2026-11-25"),
    (_et((2026, 11, 27), 10, 0), "2026-11-27"),
])
def test_session_key_skips_weekends_and_holidays(when, key):
    assert market.session_key_et(when) == key


@pytest.mark.parametrize("ymd", [SATURDAY, SUNDAY, THANKSGIVING])
def test_no_session_window_opens_on_a_closed_day(monkeypatch, ymd):
    for hh, check in ((8, market.in_premarket), (10, market.in_market_hours),
                      (17, market.in_after_hours)):
        _freeze_clock(monkeypatch, _et(ymd, hh))
        assert check() is False


def test_session_windows_still_open_on_an_exchange_day(monkeypatch):
    for hh, check in ((8, market.in_premarket), (10, market.in_market_hours),
                      (17, market.in_after_hours)):
        _freeze_clock(monkeypatch, _et((2026, 10, 16), hh))
        assert check() is True


@pytest.mark.parametrize("ymd", [SATURDAY, THANKSGIVING])
def test_closed_day_tables_are_frozen_and_hold_no_day_trade_lease(ymd):
    for hh in (4, 8, 10, 17):
        now = _et(ymd, hh)
        assert ss.session_period(now) == ss.PERIOD_CLOSED
        assert [s.table for s in ss.desired_leases(now)] == [ss.TABLE_LARGE_CAP]
        for table in (ss.TABLE_GAPPERS, ss.TABLE_GAINERS, ss.TABLE_LOSERS, ss.TABLE_AFTERHOURS):
            assert not ss.table_is_live(table, now)
            assert ss.table_should_be_frozen(table, now)
        assert ss.table_is_live(ss.TABLE_LARGE_CAP, now)  # ADR 014: a swing table, never frozen


def test_saturday_0400_keeps_fridays_frozen_board(monkeypatch):
    when = _et(SATURDAY, 4, 30)
    _freeze_clock(monkeypatch, when)
    state = ScannerRuntimeState()
    friday_rows = [{"symbol": "RUN", "price": 3.46, "prev_close": 3.01}]
    state.gainer_cache = list(friday_rows)
    state.gainer_table.state = TABLE_STATE_FROZEN
    state.gainer_table.session_key = FRIDAY

    ss.reconcile_session_tables(state, now=when)

    assert state.gainer_cache == friday_rows
    assert state.gainer_table.state == TABLE_STATE_FROZEN
    assert state.gainer_table.session_key == FRIDAY
    assert ss.is_table_frozen(state, ss.TABLE_GAINERS)


def test_monday_0400_still_rolls_over(monkeypatch):
    when = _et(MONDAY, 4, 0)
    _freeze_clock(monkeypatch, when)
    state = ScannerRuntimeState()
    state.gainer_cache = [{"symbol": "RUN"}]
    state.gainer_table.state = TABLE_STATE_FROZEN
    state.gainer_table.session_key = FRIDAY

    ss.reconcile_session_tables(state, now=when)

    assert state.gainer_cache == []
    assert state.gainer_table.session_key == "2026-10-19"


def test_closed_day_scan_loop_runs_no_discovery(monkeypatch):
    _freeze_clock(monkeypatch, _et(SATURDAY, 10, 0))
    calls: list[str] = []
    monkeypatch.setattr(scan_loop, "get_runtime_state", ScannerRuntimeState)
    monkeypatch.setattr(scan_loop._scanner_session, "reconcile_session_tables", lambda state: [])
    monkeypatch.setattr(scan_loop, "refresh_hod_momo_universe", lambda: None)
    monkeypatch.setattr(scan_loop, "_ibkr_membership_from_stream", lambda: False)
    monkeypatch.setattr(scan_loop, "_ibkr_one_shot_paused", lambda: False)
    monkeypatch.setattr(scan_loop, "run_discovery_scan", lambda: calls.append("discovery"))
    monkeypatch.setattr(scan_loop, "run_gainers_update", lambda: calls.append("gainers"))

    async def _stop(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(scan_loop.asyncio, "sleep", _stop)
    asyncio.run(scan_loop.scan_loop())

    assert calls == []
