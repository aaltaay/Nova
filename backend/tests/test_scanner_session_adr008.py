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
    assert [t for t, _ in ss.desired_leases(_et(2026, 7, 23, 8, 0))] == [
        ss.TABLE_GAINERS, ss.TABLE_GAPPERS,
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


def test_hydrate_rows_preserves_unchanged_symbols(monkeypatch):
    """Plan §2: cold reqTickersAsync hydration only for newly admitted
    symbols; unchanged symbols keep their previously-hydrated row."""
    import asyncio

    from ibkr import scanner_hydrate as hydrate

    hydrate.reset_known()
    calls: list[list[str]] = []

    async def fake_snapshot_quotes(symbols, **_kw):
        calls.append(list(symbols))
        return {s: {"price": 10.0, "prev_close": 9.0, "volume": 1} for s in symbols}

    monkeypatch.setattr(hydrate._discovery, "snapshot_quotes", fake_snapshot_quotes)

    rows1 = asyncio.run(hydrate.hydrate_rows(
        ["AAA", "BBB"], table="gainers", session_key="2026-07-23",
        as_gapper=False, reverse=True,
    ))
    assert {r["symbol"] for r in rows1} == {"AAA", "BBB"}
    assert calls == [["AAA", "BBB"]]

    # BBB re-quoted at a different price to prove it is NOT re-fetched.
    async def fake_snapshot_quotes_2(symbols, **_kw):
        calls.append(list(symbols))
        return {s: {"price": 99.0, "prev_close": 9.0, "volume": 1} for s in symbols}

    monkeypatch.setattr(hydrate._discovery, "snapshot_quotes", fake_snapshot_quotes_2)

    rows2 = asyncio.run(hydrate.hydrate_rows(
        ["AAA", "BBB", "CCC"], table="gainers", session_key="2026-07-23",
        as_gapper=False, reverse=True,
    ))
    assert calls[-1] == ["CCC"]  # only the newly admitted symbol was cold-quoted
    by_sym = {r["symbol"]: r for r in rows2}
    assert by_sym["AAA"]["price"] == 10.0  # preserved, not re-quoted
    assert by_sym["BBB"]["price"] == 10.0  # preserved, not re-quoted
    assert by_sym["CCC"]["price"] == 99.0  # newly admitted, hydrated


def test_hydrate_rows_drops_symbols_no_longer_in_batch(monkeypatch):
    import asyncio

    from ibkr import scanner_hydrate as hydrate

    hydrate.reset_known()

    async def fake_snapshot_quotes(symbols, **_kw):
        return {s: {"price": 1.0, "prev_close": 1.0, "volume": 1} for s in symbols}

    monkeypatch.setattr(hydrate._discovery, "snapshot_quotes", fake_snapshot_quotes)

    asyncio.run(hydrate.hydrate_rows(
        ["AAA", "BBB"], table="gainers", session_key="2026-07-23",
        as_gapper=False, reverse=True,
    ))
    rows = asyncio.run(hydrate.hydrate_rows(
        ["BBB"], table="gainers", session_key="2026-07-23",
        as_gapper=False, reverse=True,
    ))
    assert {r["symbol"] for r in rows} == {"BBB"}


def test_hydrate_rows_resets_on_session_rollover(monkeypatch):
    import asyncio

    from ibkr import scanner_hydrate as hydrate

    hydrate.reset_known()
    calls: list[list[str]] = []

    async def fake_snapshot_quotes(symbols, **_kw):
        calls.append(list(symbols))
        return {s: {"price": 1.0, "prev_close": 1.0, "volume": 1} for s in symbols}

    monkeypatch.setattr(hydrate._discovery, "snapshot_quotes", fake_snapshot_quotes)

    asyncio.run(hydrate.hydrate_rows(
        ["AAA"], table="gainers", session_key="2026-07-22",
        as_gapper=False, reverse=True,
    ))
    asyncio.run(hydrate.hydrate_rows(
        ["AAA"], table="gainers", session_key="2026-07-23",
        as_gapper=False, reverse=True,
    ))
    # New session — AAA must be re-quoted, not reused from the prior day.
    assert calls == [["AAA"], ["AAA"]]


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
