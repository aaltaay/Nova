"""HOD Momo's enrichment reads the live lines, then snapshots the rest within a budget, in turns (#891).

Off hours IBKR takes up to ~11 s per 5-name snapshot: the 40-name call ran past the 25 s thread
bridge on every pass since at least 2026-10-10, was cancelled, and nothing it asked for was used.
"""
from __future__ import annotations

import pytest

from ibkr import background_quotes


@pytest.fixture(autouse=True)
def _fresh():
    background_quotes.reset_for_tests()
    yield
    background_quotes.reset_for_tests()


def _live(monkeypatch, rows, *, replay=False):
    from ibkr import ticks
    import sim.mode

    monkeypatch.setattr(ticks, "last_quotes", lambda syms: {s: rows[s] for s in syms if s in rows})
    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: replay)


def test_names_with_a_live_level_1_line_are_read_from_it(monkeypatch):
    rows = {"AIXI": {"price": 3.2, "volume": 4_100_000, "prev_close": 2.4}, "SOXS": {"price": None}}
    _live(monkeypatch, rows)
    assert background_quotes.streamed(["AIXI", "SOXS", "SCNI"]) == {"AIXI": rows["AIXI"]}
    _live(monkeypatch, rows, replay=True)
    assert background_quotes.streamed(["AIXI"]) == {}


def test_each_pass_snapshots_the_longest_waiting_names_and_moves_them_back():
    names = [f"S{i:02d}" for i in range(14)]
    assert background_quotes.snapshot_turn(names, now=100.0, max_names=10) == names[:10]
    second = background_quotes.snapshot_turn(names, now=130.0, max_names=10)
    assert second[:4] == names[10:] and len(second) == 10       # the never-tried go first
    background_quotes.snapshot_turn(names[:2], now=160.0, max_names=10)
    assert set(background_quotes._tried_at) == set(names[:2])   # a name that left the set is forgotten


def test_gather_snapshots_only_the_names_without_a_live_line_within_the_budget(monkeypatch):
    from ibkr import discovery

    _live(monkeypatch, {"AIXI": {"price": 3.2, "volume": 4_100_000, "prev_close": 2.4}})
    asked: list[tuple[list[str], float | None]] = []

    async def fake_snapshot(syms, *, budget_sec=None, **_kw):
        asked.append((list(syms), budget_sec))
        return {"SCNI": {"price": 2.02, "volume": 33_900_000, "prev_close": 1.16}}

    monkeypatch.setattr(discovery, "snapshot_quotes", fake_snapshot)

    def run_ibkr(coro):
        import asyncio
        return asyncio.run(coro)

    quotes = background_quotes.gather(["AIXI", "SCNI", "FCHL"], run_ibkr=run_ibkr, budget_sec=18.0, max_names=10)
    assert asked == [(["SCNI", "FCHL"], 18.0)]
    assert sorted(quotes) == ["AIXI", "SCNI"]


def test_a_failed_snapshot_still_returns_the_live_lines(monkeypatch):
    from ibkr import discovery

    _live(monkeypatch, {"AIXI": {"price": 3.2}})

    async def fake_snapshot(syms, **_kw):
        return {}

    monkeypatch.setattr(discovery, "snapshot_quotes", fake_snapshot)
    quotes = background_quotes.gather(["AIXI", "SCNI"], run_ibkr=lambda coro: (coro.close(), None)[1],
                                      budget_sec=18.0, max_names=10)
    assert quotes == {"AIXI": {"price": 3.2}}


def test_the_enrichment_budget_fits_inside_the_thread_bridge():
    from constants import HOD_MOMO_ENRICH_SNAPSHOT_BUDGET_SEC, IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC

    assert HOD_MOMO_ENRICH_SNAPSHOT_BUDGET_SEC + 2 < IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC
