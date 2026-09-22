"""REST and /ws/scanner serve the same rows (QA C49) with an honest RVOL source (QA C39)."""
from __future__ import annotations

import asyncio
import json

import pytest

import scanner_push
import scanner_surface
from constants_scanner import SCANNER_RVOL_SOURCE_ALPACA, SCANNER_RVOL_SOURCE_YFINANCE
from fundamentals import _fundamentals_cache
from runtime_state.state import TableState


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.frames.append(json.loads(text))


@pytest.fixture
def blocklist(monkeypatch):
    blocked = {"BLOK"}
    monkeypatch.setattr(scanner_surface._hod_momo, "is_blocked", lambda s: (s or "").upper() in blocked)
    return blocked


def test_surface_strips_the_blocklist_and_scores_large_cap(blocklist):
    rows = [
        {"symbol": "NVDA", "price": 200.0, "rvol": 3.0, "atr_expansion": 2.0, "change_20d_pct": 0.1},
        {"symbol": "BLOK", "price": 5.0, "rvol": 9.0, "atr_expansion": 4.0, "change_20d_pct": 0.3},
        {"symbol": "AMD", "price": 150.0, "rvol": 1.0, "atr_expansion": 0.5, "change_20d_pct": 0.02},
    ]
    out = scanner_surface.surface_rows(rows, "large_cap")
    assert [r["symbol"] for r in out] == ["NVDA", "AMD"]
    assert all(r.get("large_cap_score") is not None for r in out)
    # Not large cap: no score is invented.
    assert "large_cap_score" not in scanner_surface.surface_rows(rows[:1], "gainers")[0]


def test_roster_replace_and_connect_snapshot_use_the_rest_surface(blocklist, monkeypatch):
    sock = _FakeSocket()
    monkeypatch.setattr(scanner_push, "_clients", {sock})
    ts = TableState()
    ts.state = "live"
    rows = [{"symbol": "GRML", "price": 9.42}, {"symbol": "BLOK", "price": 1.0}]
    asyncio.run(scanner_push.broadcast_roster_replace("gainers", rows, ts))
    assert [r["symbol"] for r in sock.frames[0]["rows"]] == ["GRML"]

    from runtime_state import get_runtime_state

    state = get_runtime_state()
    prev = state.large_cap_cache
    try:
        state.large_cap_cache = [
            {"symbol": "NVDA", "price": 200.0, "rvol": 3.0, "atr_expansion": 2.0, "change_20d_pct": 0.1},
            {"symbol": "BLOK", "price": 5.0, "rvol": 9.0},
        ]
        snap = scanner_push._snapshot_payload()
        lc = snap["large_cap"]["rows"]
        assert [r["symbol"] for r in lc] == ["NVDA"]
        assert lc[0]["large_cap_score"] is not None
    finally:
        state.large_cap_cache = prev


def test_rvol_source_names_the_average_it_divides_by(blocklist, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "GRML", {"average_volume": 1_000_000.0})
    rows = [
        # The decoration fills rel_volume from the yfinance average -> "yfinance".
        {"symbol": "GRML", "price": 9.42, "volume": 3_000_000},
        # A runner already divided by an Alpaca IEX average and said so.
        {"symbol": "TOPS", "price": 2.0, "volume": 900_000, "rel_volume": 54.29, "rvol_source": SCANNER_RVOL_SOURCE_ALPACA},
        # No average anywhere: no RVOL, no source.
        {"symbol": "NONE", "price": 1.0, "volume": 10},
    ]
    out = {r["symbol"]: r for r in scanner_surface.surface_rows(rows, "afterhours")}
    assert out["GRML"]["rel_volume"] == 3.0
    assert out["GRML"]["rvol_source"] == SCANNER_RVOL_SOURCE_YFINANCE
    assert out["TOPS"]["rvol_source"] == SCANNER_RVOL_SOURCE_ALPACA
    assert out["NONE"].get("rel_volume") is None
    assert out["NONE"].get("rvol_source") is None
    # The cached rows are not decorated in place.
    assert "rvol_source" not in rows[0]


def test_broadcast_sends_null_for_nan(monkeypatch):
    sock = _FakeSocket()
    monkeypatch.setattr(scanner_push, "_clients", {sock})
    asyncio.run(scanner_push.broadcast({"type": "price_patch", "rows": [{"symbol": "X", "price": float("nan")}]}))
    assert sock.frames[0]["rows"][0]["price"] is None
