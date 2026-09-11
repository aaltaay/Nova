"""G8: roster commit refreshes HOD active set and wakes L1 reconcile."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import hod_roster_hooks
import ibkr.scanner_hydrate as hydrate
import ibkr.scanner_l1 as scanner_l1
import ibkr_bridge
from ibkr import scanner_session as _ss
from runtime_state import ScannerRuntimeState


def test_request_reconcile_sets_event():
    ev = scanner_l1._ensure_reconcile_event()
    ev.clear()
    scanner_l1.request_reconcile()
    assert ev.is_set()
    ev.clear()


def test_on_hod_roster_commit_ignores_losers(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        ibkr_bridge, "refresh_hod_active_set", lambda: calls.append("refresh") or []
    )
    monkeypatch.setattr(
        scanner_l1, "request_reconcile", lambda: calls.append("reconcile")
    )
    hod_roster_hooks.on_hod_roster_commit(_ss.TABLE_LOSERS)
    assert calls == []


def test_on_hod_roster_commit_refreshes_and_requests(monkeypatch):
    state = ScannerRuntimeState()
    state.gainer_cache = [{"symbol": "MOVE1", "change_pct": 40.0}]
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)

    reconcile_calls: list[int] = []
    monkeypatch.setattr(
        scanner_l1,
        "request_reconcile",
        lambda: reconcile_calls.append(1),
    )

    hod_roster_hooks.on_hod_roster_commit(_ss.TABLE_GAINERS)
    assert "MOVE1" in ibkr_bridge.refresh_hod_active_set()
    assert reconcile_calls == [1]


def test_commit_table_live_hooks_hod_roster(monkeypatch):
    state = ScannerRuntimeState()
    monkeypatch.setattr(hydrate, "get_runtime_state", lambda: state)
    monkeypatch.setattr(hydrate._client, "current_generation", lambda: 1)
    monkeypatch.setattr(hydrate._session, "is_persistent_authoritative", lambda: True)
    monkeypatch.setattr(
        hydrate._session,
        "can_commit_roster",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        hydrate._session,
        "cache_attr_names",
        lambda table: ("gapper_cache", "gapper_cache_ts"),
    )
    ts = SimpleNamespace(
        state="live",
        revision=0,
        roster_ts=0.0,
        session_key="2026-07-28",
        source="",
    )
    monkeypatch.setattr(hydrate._session, "table_attr", lambda _state, _table: ts)
    monkeypatch.setattr(hydrate._session, "mark_live", lambda *a, **k: None)
    monkeypatch.setattr("ibkr.scanner_persist.persist_roster", lambda *a, **k: None)

    async def fake_hydrate(*_a, **_k):
        return [{"symbol": "NEW1", "price": 1.0, "change_pct": 20.0}]

    monkeypatch.setattr(hydrate, "hydrate_rows", fake_hydrate)

    async def fake_broadcast(*_a, **_k):
        return None

    import sys

    sys.modules.setdefault("scanner_push", MagicMock())
    sys.modules["scanner_push"].broadcast_roster_replace = fake_broadcast

    hooked: list[str] = []
    news_hooked: list[tuple[str, list]] = []
    monkeypatch.setattr(
        hod_roster_hooks,
        "on_hod_roster_commit",
        lambda table: hooked.append(table),
    )
    # commit_table imports the symbol fresh -- patch the module attribute used after import
    monkeypatch.setattr(
        "hod_roster_hooks.on_hod_roster_commit",
        lambda table: hooked.append(table),
    )
    monkeypatch.setattr(
        "scanner_news_badge.on_roster_commit",
        lambda table, rows: news_hooked.append((table, list(rows))),
    )

    ok = asyncio.run(
        hydrate.commit_table(
            table=_ss.TABLE_GAPPERS,
            symbols=["NEW1"],
            lease_generation=1,
            lease_epoch=1,
            lease_session_key="2026-07-28",
            epoch=1,
            shadow={},
        )
    )
    assert ok is True
    assert hooked == [_ss.TABLE_GAPPERS]
    assert news_hooked and news_hooked[0][0] == _ss.TABLE_GAPPERS
    assert any(r.get("symbol") == "NEW1" for r in news_hooked[0][1])
    assert any(r.get("symbol") == "NEW1" for r in (state.gapper_cache or []))
