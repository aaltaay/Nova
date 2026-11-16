"""Claude's eye (ADR 068 decisions 3 and 12). Claude's lines are its lane's (ADR 071, ``test_line_lanes_yours``).

The eye reads IBKR's Level 1 samples (``hod_momo_metrics``: the day volume and the last that came with it), the
scanner's rows and the setups universe.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

import hod_momo_metrics as metrics
from agent_trader import eye, lines, seat, watcher
from agent_trader.constants_agent_trader import (
    AGENT_EYE_SPIKE_MIN_DOLLARS,
    AGENT_EYE_SPIKE_MOVE_PCT,
    AGENT_EYE_SPIKE_SECONDS,
)

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _fresh():
    metrics.clear_volume_buffers()
    eye.reset_for_tests()
    seat.reset_for_tests()
    lines.reset_for_tests()
    watcher.reset_for_tests()
    yield
    metrics.clear_volume_buffers()
    eye.reset_for_tests()
    seat.reset_for_tests()
    lines.reset_for_tests()
    watcher.reset_for_tests()


def _trades(sym: str, rows: list[tuple[float, int, float]]) -> None:
    """(seconds before NOW, cumulative day volume, last) samples, oldest first."""
    for ago, vol, px in rows:
        metrics.update_cum_volume(sym, vol, NOW - ago, px)


# -- the samples --------------------------------------------------------------------------------------------
def test_a_window_reads_the_move_the_shares_and_each_step_at_its_own_last():
    _trades("SPKE", [(90, 1_000, 2.00), (50, 11_000, 2.02), (20, 21_000, 2.04), (1, 31_000, 2.06)])
    then, last, shares, dollars = metrics.window_trades("SPKE", 60, NOW)
    assert (then, last, shares) == (2.00, 2.06, 30_000)
    assert dollars == pytest.approx(10_000 * 2.02 + 10_000 * 2.04 + 10_000 * 2.06)
    then10, _, shares10, _ = metrics.window_trades("SPKE", 10, NOW)
    assert then10 == 2.04 and shares10 == 10_000


def test_a_window_the_samples_do_not_reach_back_across_is_unknown_not_filled_in():
    _trades("NEWB", [(30, 1_000, 3.0), (5, 2_000, 3.1)])
    assert metrics.window_trades("NEWB", 60, NOW) is None
    assert metrics.window_trades("NEWB", 10, NOW) is not None
    assert metrics.window_trades("NONE", 10, NOW) is None


def test_a_day_volume_reset_is_unknown():
    _trades("RSET", [(70, 50_000, 1.0), (30, 10, 1.1)])
    assert metrics.window_trades("RSET", 60, NOW) is None


def test_a_volume_only_sample_is_skipped_and_its_shares_land_on_the_next_priced_one():
    """Codex review on PR #1247: the quote panel writes day volume without a last."""
    _trades("PANL", [(90, 1_000, 2.00)])
    metrics.update_cum_volume("PANL", 5_000, NOW - 40)               # the quote panel: no last
    _trades("PANL", [(20, 9_000, 2.10)])
    metrics.update_cum_volume("PANL", 9_500, NOW - 1)                # the newest sample has no last either
    then, last, shares, dollars = metrics.window_trades("PANL", 60, NOW)
    assert (then, last, shares) == (2.00, 2.10, 8_000) and dollars == pytest.approx(8_000 * 2.10)
    metrics.update_cum_volume("ONLY", 100, NOW - 70)
    metrics.update_cum_volume("ONLY", 200, NOW - 10)
    assert metrics.window_trades("ONLY", 60, NOW) is None             # no last at all: unknown
    assert metrics.cum_volume_samples("ONLY") == [(NOW - 70, 100), (NOW - 10, 200)]   # the old shape stays


# -- the spike rule -----------------------------------------------------------------------------------------
def test_a_spike_is_the_rule_from_the_constants_either_way():
    big = AGENT_EYE_SPIKE_MIN_DOLLARS
    assert eye.spike_of({"pct": AGENT_EYE_SPIKE_MOVE_PCT, "dollars": big})["direction"] == "up"
    assert eye.spike_of({"pct": -AGENT_EYE_SPIKE_MOVE_PCT - 1, "dollars": big})["direction"] == "down"
    assert eye.spike_of({"pct": AGENT_EYE_SPIKE_MOVE_PCT - 0.01, "dollars": big * 10}) is None
    assert eye.spike_of({"pct": 10.0, "dollars": big - 1}) is None
    assert eye.spike_of(None) is None


# -- the whole market ---------------------------------------------------------------------------------------
@pytest.fixture
def market(monkeypatch):
    """Two Gappers rows, one setups-only symbol; IBKR's Level 1 faked by symbol."""
    import hod_momo_active
    import scanner_surface
    from catalysts import board
    from ibkr import ticks
    from runtime_state import get_runtime_state

    state = get_runtime_state()
    monkeypatch.setattr(state, "gapper_cache", [{"symbol": "SPKE", "float_shares": 3_000_000},
                                                {"symbol": "SLOW", "float_shares": 9_000_000}])
    monkeypatch.setattr(state, "gainer_cache", [{"symbol": "SPKE"}])
    monkeypatch.setattr(state, "afterhours_cache", [])
    monkeypatch.setattr(hod_momo_active, "get_active_symbols", lambda: ["SETU", "SPKE"])
    monkeypatch.setattr(scanner_surface, "surface_rows",
                        lambda rows, table=None: [{**r, "halted": r["symbol"] == "SLOW"} for r in rows])
    quotes = {"SPKE": {"price": 2.10, "prev_close": 1.50}, "SLOW": {"price": 5.05, "prev_close": 5.00},
              "SETU": {"price": 7.00, "prev_close": 7.00, "quote_quality": "close_fallback"}}
    monkeypatch.setattr(ticks, "last_quotes", lambda syms=None: {s: quotes[s] for s in (syms or quotes) if s in quotes})
    monkeypatch.setattr(ticks, "bid_ask", lambda s: (2.09, 2.11) if s == "SPKE" else (None, None))
    monkeypatch.setattr(board, "_verdicts", {"SPKE": {"verdict": "real", "category": "fda", "strength": "strong",
                                                      "title": "FDA nod", "published_ts": NOW - 600, "url": "x"}})
    _trades("SPKE", [(90, 100_000, 2.00), (40, 150_000, 2.05), (1, 200_000, 2.10)])   # +5% on $207,500
    _trades("SLOW", [(90, 10_000, 5.00), (1, 11_000, 5.05)])                           # +1%
    return quotes


def test_the_eye_sees_every_symbol_with_its_lists_and_ranks_spikes_first(market):
    ranked = eye.rows(NOW)
    assert [r["symbol"] for r in ranked] == ["SPKE", "SLOW", "SETU"]
    spke = ranked[0]
    assert spke["lists"] == ["gappers", "gainers", "setups"]
    assert spke["spike"]["direction"] == "up" and spke["spike"]["pct"] == pytest.approx(5.0)
    assert spke["windows"][str(AGENT_EYE_SPIKE_SECONDS)]["dollars"] == pytest.approx(50_000 * 2.05 + 50_000 * 2.10)
    assert spke["day_pct"] == pytest.approx(40.0) and spke["float_shares"] == 3_000_000
    assert spke["spread"] == pytest.approx(0.02) and spke["spread_pct"] == pytest.approx(0.02 / 2.10 * 100)
    assert spke["catalyst"] == {"verdict": "real", "category": "fda", "strength": "strong", "title": "FDA nod",
                                "published_ts": NOW - 600}
    slow = ranked[1]
    assert slow["spike"] is None and slow["halted"] is True and slow["catalyst"] is None
    setu = ranked[2]
    assert setu["lists"] == ["setups"] and setu["last"] is None and setu["day_pct"] is None   # the prior close only
    assert setu["windows"] == {"10": None, "30": None, "60": None}                           # no samples: unknown


def test_a_spike_is_listed_once_and_again_only_after_it_stopped(market):
    eye.scan(NOW)
    eye.scan(NOW + 0.5)
    assert [e["symbol"] for e in eye.events()] == ["SPKE"]
    metrics.clear_volume_buffers()
    eye.scan(NOW + 1)                                                   # no longer spiking
    _trades("SPKE", [(90, 100_000, 2.00), (1, 200_000, 2.10)])
    eye.scan(NOW + 2)
    assert [e["symbol"] for e in eye.events()] == ["SPKE", "SPKE"]
    assert eye.events()[0]["at"] == NOW + 2                              # newest first


def test_the_eye_route_answers_and_long_polls_until_a_spike(market, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(eye, "time", SimpleNamespace(time=lambda: NOW, monotonic=time.monotonic))
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    from main import app

    got = TestClient(app).get("/api/agent/trader/eye")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["source"] == "ibkr" and body["universe"] == 3 and body["symbols"][0]["symbol"] == "SPKE"
    assert body["rule"] == {"move_pct": AGENT_EYE_SPIKE_MOVE_PCT, "seconds": AGENT_EYE_SPIKE_SECONDS,
                            "min_dollars": AGENT_EYE_SPIKE_MIN_DOLLARS}
    eye.reset_for_tests()
    waited = asyncio.run(eye.eye(wait=5, after=NOW - 1))               # a spike newer than ``after``: at once
    assert [e["symbol"] for e in waited["spikes"]] == ["SPKE"]
    assert TestClient(app).get("/api/agent/trader/eye?wait=31").status_code == 422
