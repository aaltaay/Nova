"""ADR 008 authoritative commits must write dated scanner JSON."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import hod_roster_hooks
import ibkr.scanner_hydrate as hydrate
from ibkr import scanner_persist
from ibkr import scanner_session as _ss
from runtime_state import ScannerRuntimeState


def test_persist_roster_writes_dated_gappers(tmp_path, monkeypatch):
    monkeypatch.setattr("cache._CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("cache._today_et", lambda: "2026-08-17")
    scanner_persist.persist_roster(
        _ss.TABLE_GAPPERS,
        [{"symbol": "IVF", "gap_percent": 0.4}],
        1.0,
    )
    path = tmp_path / "gappers-2026-08-17.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["date"] == "2026-08-17"
    assert data["gappers"][0]["symbol"] == "IVF"


def test_commit_table_persists_authoritative_roster(tmp_path, monkeypatch):
    monkeypatch.setattr("cache._CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("cache._today_et", lambda: "2026-08-17")
    state = ScannerRuntimeState()
    monkeypatch.setattr(hydrate, "get_runtime_state", lambda: state)
    monkeypatch.setattr(hydrate._client, "current_generation", lambda: 1)
    monkeypatch.setattr(hydrate._session, "is_persistent_authoritative", lambda: True)
    monkeypatch.setattr(hydrate._session, "can_commit_roster", lambda *a, **k: True)
    monkeypatch.setattr(
        hydrate._session,
        "cache_attr_names",
        lambda table: ("gapper_cache", "gapper_cache_ts"),
    )
    ts = SimpleNamespace(
        state="live",
        revision=0,
        roster_ts=0.0,
        session_key="2026-08-17",
        source="",
    )
    monkeypatch.setattr(hydrate._session, "table_attr", lambda _state, _table: ts)
    monkeypatch.setattr(hydrate._session, "mark_live", lambda *a, **k: None)

    async def fake_hydrate(*_a, **_k):
        return [{"symbol": "NEW1", "price": 1.0, "gap_percent": 0.2}]

    monkeypatch.setattr(hydrate, "hydrate_rows", fake_hydrate)
    import sys

    async def fake_broadcast(*_a, **_k):
        return None

    sys.modules.setdefault("scanner_push", MagicMock())
    sys.modules["scanner_push"].broadcast_roster_replace = fake_broadcast
    monkeypatch.setattr(hod_roster_hooks, "on_hod_roster_commit", lambda table: None)
    monkeypatch.setattr("hod_roster_hooks.on_hod_roster_commit", lambda table: None)

    ok = asyncio.run(
        hydrate.commit_table(
            table=_ss.TABLE_GAPPERS,
            symbols=["NEW1"],
            lease_generation=1,
            lease_epoch=1,
            lease_session_key="2026-08-17",
            epoch=1,
            shadow={},
        )
    )
    assert ok is True
    path = tmp_path / "gappers-2026-08-17.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["gappers"][0]["symbol"] == "NEW1"
