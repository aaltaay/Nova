"""ADR 008 session windows, freeze, fencing, and desired leases."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ibkr import scanner_session as ss
from market import session_key_et
from runtime_state.state import (
    TABLE_STATE_FROZEN,
    TABLE_STATE_LIVE,
    ScannerRuntimeState,
)

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def test_session_key_midnight_belongs_to_prior_session():
    # 2026-07-23 02:00 ET → prior session 2026-07-22
    assert session_key_et(_et(2026, 7, 23, 2, 0)) == "2026-07-22"
    assert session_key_et(_et(2026, 7, 23, 4, 0)) == "2026-07-23"
    assert session_key_et(_et(2026, 7, 23, 9, 29)) == "2026-07-23"


def test_desired_leases_by_period():
    # Premarket holds one lease: TOP_OPEN_PERC_GAIN has no open to measure
    # before 09:30 (IB Warning 165), so Gappers is projected from Gainers.
    assert [t for t, _ in ss.desired_leases(_et(2026, 7, 23, 8, 0))] == [
        ss.TABLE_GAINERS,
    ]
    assert [t for t, _ in ss.desired_leases(_et(2026, 7, 23, 10, 0))] == [
        ss.TABLE_GAINERS, ss.TABLE_LOSERS,
    ]
    assert [t for t, _ in ss.desired_leases(_et(2026, 7, 23, 17, 0))] == [
        ss.TABLE_AFTERHOURS,
    ]
    assert ss.desired_leases(_et(2026, 7, 23, 21, 0)) == []


def test_gappers_live_then_freeze_at_0930():
    assert ss.table_is_live(ss.TABLE_GAPPERS, _et(2026, 7, 23, 9, 29))
    assert not ss.table_is_live(ss.TABLE_GAPPERS, _et(2026, 7, 23, 9, 30))
    assert ss.table_should_be_frozen(ss.TABLE_GAPPERS, _et(2026, 7, 23, 9, 30))


def test_freeze_idempotent_and_blocks_commit(monkeypatch):
    state = ScannerRuntimeState()
    state.gapper_cache = [{"symbol": "AAA", "price": 1.0}]
    monkeypatch.setattr(ss, "session_key_et", lambda now=None: "2026-07-23")
    monkeypatch.setattr(ss, "table_is_live", lambda table, now=None: False)
    monkeypatch.setattr(ss, "table_should_be_frozen", lambda table, now=None: True)

    assert ss.freeze_table(state, ss.TABLE_GAPPERS) is True
    assert state.gapper_table.state == TABLE_STATE_FROZEN
    assert ss.freeze_table(state, ss.TABLE_GAPPERS) is False  # idempotent

    assert not ss.can_commit_roster(
        state, ss.TABLE_GAPPERS,
        generation=1, epoch=1, fence_generation=1, fence_epoch=1,
        session_key="2026-07-23",
    )


def test_stale_generation_rejected(monkeypatch):
    state = ScannerRuntimeState()
    monkeypatch.setattr(ss, "session_key_et", lambda now=None: "2026-07-23")
    monkeypatch.setattr(ss, "table_is_live", lambda table, now=None: True)
    state.gapper_table.state = TABLE_STATE_LIVE
    state.gapper_table.session_key = "2026-07-23"
    assert not ss.can_commit_roster(
        state, ss.TABLE_GAPPERS,
        generation=2, epoch=1, fence_generation=1, fence_epoch=1,
        session_key="2026-07-23",
    )


def test_rollover_clears_prior_session(monkeypatch):
    state = ScannerRuntimeState()
    state.gapper_cache = [{"symbol": "OLD"}]
    state.gapper_table.state = TABLE_STATE_FROZEN
    state.gapper_table.session_key = "2026-07-22"
    monkeypatch.setattr(ss, "session_key_et", lambda now=None: "2026-07-23")
    # 08:00 — gappers live window for new session
    frozen = ss.reconcile_session_tables(state, now=_et(2026, 7, 23, 8, 0))
    assert state.gapper_cache == []
    assert state.gapper_table.session_key == "2026-07-23"
    assert frozen == [] or ss.TABLE_GAPPERS not in frozen


def test_hydrate_rows_preserves_unchanged_symbols():
    """L1-filled rows survive the next IB batch; new names join as stubs.

    ADR 010 decision 5: admission is name-only, so the price a row already
    carries comes from the L1 hot path and must not be discarded when IB
    re-ranks the scan.
    """
    import asyncio

    from ibkr import scanner_hydrate as hydrate

    live = [
        {"symbol": "AAA", "rank": 1, "price": 10.0, "prev_close": 9.0},
        {"symbol": "BBB", "rank": 2, "price": 10.0, "prev_close": 9.0},
    ]

    rows2 = asyncio.run(hydrate.hydrate_rows(
        ["AAA", "BBB", "CCC"], table="gainers", session_key="2026-07-23",
        existing=live,
    ))
    by_sym = {r["symbol"]: r for r in rows2}
    assert by_sym["CCC"]["price"] is None  # newly admitted, awaiting first L1 tick
    assert by_sym["AAA"]["price"] == 10.0  # preserved L1 fill
    assert by_sym["BBB"]["price"] == 10.0  # preserved L1 fill
    assert [r["rank"] for r in rows2] == [1, 2, 3]  # rank follows the fresh batch


def test_hydrate_rows_drops_symbols_no_longer_in_batch():
    import asyncio

    from ibkr import scanner_hydrate as hydrate

    live = [
        {"symbol": "AAA", "rank": 1, "price": 1.0, "prev_close": 1.0},
        {"symbol": "BBB", "rank": 2, "price": 1.0, "prev_close": 1.0},
    ]
    rows = asyncio.run(hydrate.hydrate_rows(
        ["BBB"], table="gainers", session_key="2026-07-23", existing=live,
    ))
    assert {r["symbol"] for r in rows} == {"BBB"}


def test_hydrate_rows_carries_no_cross_session_memory():
    """Rollover clears the table cache; hydrate must not resurrect it.

    Previously hydrate kept its own per-session ``_known_rows`` map, so a
    session-key change was what forced a re-quote. The table cache is now the
    only roster memory, and ``reconcile_session_tables`` empties it at 04:00
    ET -- so a fresh session starts from stubs with no hidden state.
    """
    import asyncio

    from ibkr import scanner_hydrate as hydrate

    rows = asyncio.run(hydrate.hydrate_rows(
        ["AAA"], table="gainers", session_key="2026-07-23", existing=[],
    ))
    assert rows[0]["price"] is None


def test_recover_skips_persistent_leases(monkeypatch):
    from ibkr import discovery

    class _FakeScanDataList:
        def __init__(self, req_id):
            self.reqId = req_id

    class _FakeIB:
        def __init__(self):
            self.cancelled = []
            self.wrapper = type("W", (), {"reqId2Subscriber": {
                11: _FakeScanDataList(11),
                22: _FakeScanDataList(22),
            }})()
            self.client = self

        def cancelScannerSubscription(self, sub):
            self.cancelled.append(getattr(sub, "reqId", sub))

    monkeypatch.setattr(discovery, "_ScanDataList", _FakeScanDataList)
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(
        "ibkr.scanner_stream.persistent_reqids", lambda: {11},
    )
    ib = _FakeIB()
    recovered = discovery.recover_scanner_slots(ib)
    assert recovered == 1
    assert 11 not in ib.cancelled
    assert 22 in ib.cancelled
