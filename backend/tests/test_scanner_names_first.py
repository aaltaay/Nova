"""ADR 010 decision 5 -- scanner roster admission must not need a cold quote.

Regression suite for the 2026-08-24 premarket outage: IB delivered ranked
scanner names, ``hydrate_rows`` blocked every row behind a COLD
``snapshot_quotes`` batch, that batch kept timing out on the 20s ``on_ib``
bridge, and ``gainer_cache_ts`` stayed 0 all morning while integrity reported
``scanner_gainers=pass``. Each test below fails against the pre-fix code.
"""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import ibkr.discovery as _discovery
import ibkr.scanner_hydrate as hydrate
from constants import GAPPER_MIN_GAP_PCT
from hod_momo_integrity_scanner import evaluate_scanner_integrity
from ibkr import scanner_session as _ss
from runtime_state import ScannerRuntimeState


def _boom_snapshot(*_a, **_k):
    raise AssertionError("roster admission must not call snapshot_quotes")


async def _timeout_snapshot(*_a, **_k):
    raise asyncio.TimeoutError("IB on_ib timed out after 20.0s [snapshot_quotes]")


def test_admission_module_never_references_cold_quotes():
    """Structural guard: the gate must not come back by way of a lazy import.

    Checks executable code only -- the module docstring names
    ``snapshot_quotes`` on purpose to explain why it is banned here.
    """
    import ast

    tree = ast.parse(inspect.getsource(hydrate))
    referenced = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert "snapshot_quotes" not in referenced
    assert not hasattr(hydrate, "_discovery")


def _commit_env(monkeypatch, state):
    """Wire commit_table onto a test-owned state with an open, live lease."""
    marked: list[str] = []
    ts = SimpleNamespace(
        state="unavailable",
        revision=0,
        roster_ts=0.0,
        quote_ts=0.0,
        session_key="2026-08-24",
        source="",
        frozen_at=0.0,
    )
    monkeypatch.setattr(hydrate, "get_runtime_state", lambda: state)
    monkeypatch.setattr(hydrate._client, "current_generation", lambda: 1)
    monkeypatch.setattr(hydrate._session, "is_persistent_authoritative", lambda: True)
    monkeypatch.setattr(hydrate._session, "can_commit_roster", lambda *a, **k: True)
    monkeypatch.setattr(hydrate._session, "table_attr", lambda _s, _t: ts)
    monkeypatch.setattr(
        hydrate._session,
        "mark_live",
        lambda _ts, **k: marked.append(k.get("source", "")),
    )
    monkeypatch.setattr("ibkr.scanner_persist.persist_roster", lambda *a, **k: None)
    return ts, marked


def test_hydrate_admits_names_without_cold_quote(monkeypatch):
    """IB gave us ranked names -- that alone is enough to be a row."""
    monkeypatch.setattr(_discovery, "snapshot_quotes", _boom_snapshot)

    rows = asyncio.run(hydrate.hydrate_rows(
        ["AAA", "BBB"], table=_ss.TABLE_GAINERS, session_key="2026-08-24",
    ))

    assert [r["symbol"] for r in rows] == ["AAA", "BBB"]
    # Unpriced is honest; 0.00 would be a lie until the first L1 tick.
    assert all(r["price"] is None for r in rows)
    assert all(r["change_pct"] is None for r in rows)


def test_hydrate_preserves_ib_rank_order(monkeypatch):
    """IB already ranked the scan; local re-sorting invents a second truth."""
    monkeypatch.setattr(_discovery, "snapshot_quotes", _boom_snapshot)

    rows = asyncio.run(hydrate.hydrate_rows(
        ["CCC", "AAA", "BBB"], table=_ss.TABLE_GAINERS, session_key="2026-08-24",
    ))

    assert [r["symbol"] for r in rows] == ["CCC", "AAA", "BBB"]
    assert [r["rank"] for r in rows] == [1, 2, 3]


def test_commit_table_survives_dead_cold_quote_path(monkeypatch):
    """The exact 2026-08-24 failure: cold snapshots time out forever."""
    state = ScannerRuntimeState()
    ts, marked = _commit_env(monkeypatch, state)
    monkeypatch.setattr(_discovery, "snapshot_quotes", _timeout_snapshot)

    committed = asyncio.run(hydrate.commit_table(
        table=_ss.TABLE_GAINERS,
        symbols=["AAA", "BBB"],
        lease_generation=1,
        lease_epoch=1,
        lease_session_key="2026-08-24",
        epoch=1,
        shadow={},
    ))

    assert committed is True
    assert [r["symbol"] for r in state.gainer_cache] == ["AAA", "BBB"]
    assert state.gainer_cache_ts > 0, "a dead cold path must not zero the roster clock"
    assert marked, "table must be marked live once names are committed"


def test_commit_table_ws_failure_keeps_rest_revision(monkeypatch):
    """D-026: WS throw after persist must not report commit failure."""
    state = ScannerRuntimeState()
    ts, marked = _commit_env(monkeypatch, state)
    hydrate.reset_roster_push_failed_for_tests()

    async def boom(*_a, **_k):
        raise RuntimeError("ws down")

    monkeypatch.setattr("scanner_push.broadcast_roster_replace", boom)

    committed = asyncio.run(hydrate.commit_table(
        table=_ss.TABLE_GAINERS,
        symbols=["AAA"],
        lease_generation=1,
        lease_epoch=1,
        lease_session_key="2026-08-24",
        epoch=1,
        shadow={},
    ))

    assert committed is True
    assert [r["symbol"] for r in state.gainer_cache] == ["AAA"]
    assert ts.revision == 1
    assert marked, "REST roster is live even when the desk push raises"
    assert hydrate.roster_push_failed_count() == 1


def test_commit_table_empty_batch_does_not_mark_live(monkeypatch):
    """IB Warning 165 / no items is not a quiet market -- never stamp live."""
    state = ScannerRuntimeState()
    ts, marked = _commit_env(monkeypatch, state)

    committed = asyncio.run(hydrate.commit_table(
        table=_ss.TABLE_GAINERS,
        symbols=[],
        lease_generation=1,
        lease_epoch=1,
        lease_session_key="2026-08-24",
        epoch=1,
        shadow={},
    ))

    assert committed is None
    assert state.gainer_cache_ts == 0.0
    assert marked == []
    assert ts.state != "live"


def test_integrity_fails_for_dead_gainers_in_premarket():
    """last_gainer_scan=0 while IB is connected was reported as pass."""
    report = evaluate_scanner_integrity({
        "discovery_provider": "ibkr",
        "ibkr_connected": True,
        "current_mode": "premarket",
        "gapper_count": 0,
        "gainer_count": 0,
        "loser_count": 0,
        "gapper_age_sec": None,
        "gainer_age_sec": None,
        "loser_age_sec": None,
    })

    gainers = next(c for c in report["checks"] if c["id"] == "scanner_gainers")
    assert gainers["status"] == "fail"
    assert report["status"] == "fail"


def test_gapper_view_selects_only_rows_meeting_min_gap():
    from ibkr import gapper_view

    rows = gapper_view.derive_rows([
        {"symbol": "BIG", "price": 6.0, "prev_close": 3.0, "change_pct": 1.0},
        {"symbol": "SMALL", "price": 10.1, "prev_close": 10.0, "change_pct": 0.01},
    ])

    assert [r["symbol"] for r in rows] == ["BIG"]
    assert rows[0]["gap_percent"] == 1.0
    assert rows[0]["previous_close"] == 3.0
    assert rows[0]["current_price"] == 6.0
    assert GAPPER_MIN_GAP_PCT <= rows[0]["gap_percent"] * 100


def test_gapper_view_ignores_unpriced_stub_rows():
    from ibkr import gapper_view

    rows = gapper_view.derive_rows([
        {"symbol": "WAIT", "price": None, "prev_close": None, "change_pct": None},
    ])

    assert rows == []


def test_premarket_leases_are_gainers_only():
    """TOP_OPEN_PERC_GAIN has no open to measure before 09:30 (IB Warning 165).

    Large Cap (ADR 014) is present too -- it is an always-live swing table,
    not a day-trade discovery lease, so it does not break "gainers only" for
    the day-trade leases this test is actually about.
    """
    from datetime import datetime

    from market import ET

    premarket = datetime(2026, 8, 24, 8, 30, tzinfo=ET)
    leases = _ss.desired_leases(premarket)

    assert [spec.table for spec in leases] == [_ss.TABLE_GAINERS, _ss.TABLE_LARGE_CAP]
