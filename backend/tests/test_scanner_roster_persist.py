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


def test_persist_roster_does_not_overwrite_nonempty_with_empty(tmp_path, monkeypatch):
    """A names-first Gainers replace can project zero gappers for a few
    seconds. That must not wipe the day's history file (2026-08-24)."""
    monkeypatch.setattr("cache._CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("cache._today_et", lambda: "2026-08-24")
    scanner_persist.persist_roster(
        _ss.TABLE_GAPPERS,
        [{"symbol": "CRE", "gap_percent": 0.4}],
        1.0,
    )
    scanner_persist.persist_roster(_ss.TABLE_GAPPERS, [], 2.0)
    data = json.loads((tmp_path / "gappers-2026-08-24.json").read_text(encoding="utf-8"))
    assert data["gappers"][0]["symbol"] == "CRE"
    assert data["ts"] == 1.0


def test_load_snapshot_movers_composes_gainers_and_losers(tmp_path, monkeypatch):
    import cache as cache_mod

    monkeypatch.setattr("cache._CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("cache._today_et", lambda: "2026-08-24")
    cache_mod.save_gainer_snapshot([{"symbol": "AAA"}], 10.0)
    cache_mod.save_loser_snapshot([{"symbol": "BBB"}], 11.0)
    data = cache_mod.load_snapshot_for_date("movers", "2026-08-24")
    assert data["gainers"][0]["symbol"] == "AAA"
    assert data["losers"][0]["symbol"] == "BBB"


def test_list_history_dates_skips_empty_snapshots(tmp_path, monkeypatch):
    import cache as cache_mod

    monkeypatch.setattr("cache._CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("cache._today_et", lambda: "2026-08-26")
    (tmp_path / "gappers-2026-08-24.json").write_text(
        '{"date":"2026-08-24","ts":1,"gappers":[]}', encoding="utf-8"
    )
    (tmp_path / "gappers-2026-08-25.json").write_text(
        '{"date":"2026-08-25","ts":1,"gappers":[{"symbol":"CRE"}]}',
        encoding="utf-8",
    )
    assert cache_mod.list_history_dates("gappers") == ["2026-08-25"]


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

    # monkeypatch, not a bare attribute write: the old write outlived the test
    # and replaced the real broadcast for every test after it.
    monkeypatch.setattr("scanner_push.broadcast_roster_replace", fake_broadcast)
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
