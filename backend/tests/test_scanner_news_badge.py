"""Scanner NEWS badge under discovery=ibkr (D-001 / #45).

Alpaca-era movers/discovery runners early-return when discovery is ibkr, so
nothing wrote ``has_news`` / ``newest_headline_at``. The badge cache is a
side view: decorate at serialization time, never mutate a frozen roster row.
"""
from __future__ import annotations

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mover_enrich_view as mev  # noqa: E402
import scanner_news_badge as snb  # noqa: E402
from runtime_state import get_runtime_state  # noqa: E402


def _ibkr(monkeypatch):
    monkeypatch.setattr("alpaca._get_discovery_provider", lambda: "ibkr")


def test_decorate_rows_stamps_news_from_badge_cache(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    snb.record({"cre": "2026-09-11T12:00:00Z"})
    rows = [{"symbol": "CRE", "volume": 10}]
    out = mev.decorate_rows(rows)
    assert out[0]["has_news"] is True
    assert out[0]["newest_headline_at"] == "2026-09-11T12:00:00Z"
    # ADR 008: frozen roster row must stay untouched.
    assert rows[0] == {"symbol": "CRE", "volume": 10}


def test_decorate_rows_does_not_clobber_existing_headline(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    snb.record({"CRE": "2026-09-11T18:00:00Z"})
    out = mev.decorate_rows([{
        "symbol": "CRE",
        "has_news": True,
        "newest_headline_at": "2026-09-11T08:00:00Z",
    }])
    assert out[0]["newest_headline_at"] == "2026-09-11T08:00:00Z"


def test_decorate_rows_fills_false_when_cache_empty(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    out = mev.decorate_rows([{"symbol": "ZZZ"}])
    assert out[0]["has_news"] is False
    assert out[0]["newest_headline_at"] is None


def test_on_roster_commit_is_single_flight(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    batches: list[list[str]] = []
    entered = threading.Event()
    gate = threading.Event()

    def fake_check(symbols, headers):
        batches.append(list(symbols))
        entered.set()
        gate.wait(timeout=5)
        return {symbols[0]: "2026-09-11T12:00:00Z"} if symbols else {}

    monkeypatch.setattr(snb, "_alpaca_headers", lambda: {"k": "v"})
    monkeypatch.setattr(snb, "_check_news", fake_check)

    snb.on_roster_commit("gainers", [{"symbol": "AAA"}])
    first = snb._worker
    assert first is not None
    assert entered.wait(timeout=5)

    snb.on_roster_commit("losers", [{"symbol": "BBB"}])
    snb.on_roster_commit("afterhours", [{"symbol": "CCC"}])
    assert snb._worker is first
    assert snb._pending == {"BBB", "CCC"}

    gate.set()
    first.join(timeout=5)
    assert batches[0] == ["AAA"]
    assert batches[1] == ["BBB", "CCC"]
    assert snb.headline_for("AAA") == "2026-09-11T12:00:00Z"


def test_on_roster_commit_ignores_large_cap(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    snb.on_roster_commit("large_cap", [{"symbol": "AAPL"}])
    assert snb._pending == set()
    assert snb._worker is None


def test_on_roster_commit_accepts_gappers(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    monkeypatch.setattr(snb, "_alpaca_headers", lambda: None)
    snb.on_roster_commit("gappers", [{"symbol": "GAP"}])
    assert "GAP" in snb._pending or snb.headline_for("GAP") is None
    # No Alpaca keys: worker drains pending and exits without writing headlines.
    worker = snb._worker
    if worker is not None:
        worker.join(timeout=5)
    assert snb._pending == set()
    assert snb.headline_for("GAP") is None


def test_on_roster_commit_noops_when_not_ibkr(monkeypatch):
    monkeypatch.setattr("alpaca._get_discovery_provider", lambda: "alpaca")
    snb.reset_for_testing()
    snb.on_roster_commit("gainers", [{"symbol": "AAA"}])
    assert snb._pending == set()
    assert snb._worker is None


def test_queue_current_roster_gathers_four_tables_not_large_cap(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    state = get_runtime_state()
    state.gapper_cache = [{"symbol": "G1"}]
    state.gainer_cache = [{"symbol": "N1"}]
    state.loser_cache = [{"symbol": "L1"}]
    state.afterhours_cache = [{"symbol": "A1"}]
    state.large_cap_cache = [{"symbol": "AAPL"}]
    monkeypatch.setattr(snb, "_alpaca_headers", lambda: None)
    snb.queue_current_roster()
    worker = snb._worker
    if worker is not None:
        worker.join(timeout=5)
    assert snb._pending == set()
    # Keys missing means we queued then drained with no headers; large cap
    # must never have been queued (would still be pending if worker skipped it
    # after start). Prove gather itself excluded AAPL:
    gathered = snb.roster_symbols()
    assert gathered == {"G1", "N1", "L1", "A1"}
    assert "AAPL" not in gathered


def test_check_news_is_chunked(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    sizes: list[int] = []

    def fake_check(symbols, headers):
        sizes.append(len(symbols))
        return {}

    monkeypatch.setattr(snb, "_alpaca_headers", lambda: {"k": "v"})
    monkeypatch.setattr(snb, "_check_news", fake_check)
    monkeypatch.setattr(snb, "NEWS_BADGE_SYMBOL_BATCH", 2)
    snb.on_roster_commit("gainers", [
        {"symbol": "A"}, {"symbol": "B"}, {"symbol": "C"},
    ])
    worker = snb._worker
    assert worker is not None
    worker.join(timeout=5)
    assert sizes == [2, 1]


def test_date_rollover_drops_yesterdays_headlines(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    monkeypatch.setattr(snb, "_now_et", lambda: datetime(2026, 9, 10, 16, 0, tzinfo=et))
    snb.record({"CRE": "2026-09-10T12:00:00Z"})
    assert snb.headline_for("CRE") == "2026-09-10T12:00:00Z"
    monkeypatch.setattr(snb, "_now_et", lambda: datetime(2026, 9, 11, 4, 5, tzinfo=et))
    assert snb.headline_for("CRE") is None


def test_missed_refresh_does_not_wipe_known_headline(monkeypatch):
    _ibkr(monkeypatch)
    snb.reset_for_testing()
    snb.record({"CRE": "2026-09-11T12:00:00Z"})

    def fake_check(symbols, headers):
        return {}

    monkeypatch.setattr(snb, "_alpaca_headers", lambda: {"k": "v"})
    monkeypatch.setattr(snb, "_check_news", fake_check)
    snb.on_roster_commit("gainers", [{"symbol": "CRE"}])
    worker = snb._worker
    assert worker is not None
    worker.join(timeout=5)
    assert snb.headline_for("CRE") == "2026-09-11T12:00:00Z"
