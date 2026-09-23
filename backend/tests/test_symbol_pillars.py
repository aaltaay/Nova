"""The quote panel grades any symbol's Five Pillars (operator ask, 2026-09-23).

``GET /api/strategy/watchlist/{symbol}`` answers for a symbol the ranked
watchlist does not hold: its own scanner row from whichever board has it, else
its live L1 quote decorated the way the Scanner decorates rows. Unknown facts
fail their pillar with the reason; nothing is invented.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.strategy as strategy_routes  # noqa: E402
import scanner_news_badge as snb  # noqa: E402
import scanner_surface  # noqa: E402
from fundamentals import _fundamentals_cache  # noqa: E402
from runtime_state import get_runtime_state  # noqa: E402
from strategy.symbol_pillars import quote_row  # noqa: E402

BOARDS = ("gapper_cache", "gainer_cache", "loser_cache", "afterhours_cache", "large_cap_cache")


@pytest.fixture
def desk(monkeypatch):
    monkeypatch.setattr("alpaca._get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scanner_surface._hod_momo, "is_blocked", lambda s: (s or "").upper() == "BLOK")
    monkeypatch.setattr("catalysts.live.request", lambda symbols: None)
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: None)
    monkeypatch.setattr(strategy_routes, "_live_quote", lambda symbol: None)
    snb.reset_for_testing()
    state = get_runtime_state()
    prev = {name: getattr(state, name) for name in BOARDS}
    for name in BOARDS:
        setattr(state, name, [])
    yield state
    for name, rows in prev.items():
        setattr(state, name, rows)
    snb.reset_for_testing()


def _pillars(body: dict) -> dict[str, dict]:
    return {p["name"]: p for p in body["entry"]["five_pillars"]["pillars"]}


def test_a_ranked_gainer_answers_with_its_rank(desk, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "GRML", {"average_volume": 100_000.0, "float_shares": 3_100_000})
    desk.gainer_cache = [
        {"symbol": "GRML", "price": 8.61, "change_pct": 0.427, "volume": 1_820_000},
        {"symbol": "SLOW", "price": 4.00, "change_pct": 0.05, "volume": 10},
    ]

    body = strategy_routes.watchlist_one("grml")

    assert body["symbol"] == "GRML"
    assert body["source"] == "gainers"
    assert body["rank"] == 1
    assert _pillars(body)["relative_volume"]["passed"] is True  # 18.2x, decorated as the board shows it
    assert body["entry"]["float_shares"] == 3_100_000


def test_a_loser_is_graded_from_its_own_row_and_is_not_ranked(desk):
    desk.loser_cache = [{"symbol": "DOWN", "price": 6.0, "change_pct": -0.31, "volume": 900_000}]

    body = strategy_routes.watchlist_one("DOWN")

    assert body["source"] == "losers"
    assert body["rank"] is None
    assert _pillars(body)["change_pct"]["passed"] is False
    assert _pillars(body)["change_pct"]["detail"].startswith("-31.0%")


def test_a_symbol_on_no_board_is_graded_from_its_live_quote(desk, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "WHLR", {"average_volume": 300_000.0, "float_shares": 53_650})
    monkeypatch.setattr(
        strategy_routes, "_live_quote",
        lambda symbol: {"price": 5.13, "prev_close": 1.87, "volume": 82_900_000} if symbol == "WHLR" else None,
    )
    verdict = {"verdict": "catalyst", "category": "contract", "strength": "strong", "title": "Wins contract",
               "source": "prnewswire", "published_ts": 1_790_000_000.0, "news_pending": False}
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: verdict if symbol == "WHLR" else None)

    body = strategy_routes.watchlist_one("WHLR")
    pillars = _pillars(body)

    assert body["source"] == "quote"
    assert body["rank"] is None
    assert pillars["price"]["passed"] is True
    assert pillars["change_pct"]["detail"].startswith("174.3%")  # past +100%, never read as 1.7%
    assert pillars["relative_volume"]["detail"].startswith("276.3x")
    assert pillars["float"]["passed"] is True
    assert pillars["catalyst"]["passed"] is True  # the verdict is read before grading
    assert body["entry"]["five_pillars"]["pass_count"] == 5
    assert body["entry"]["catalyst"]["verdict"] == "catalyst"


def test_no_quote_is_stated_never_invented(desk):
    body = strategy_routes.watchlist_one("NOPE")
    pillars = _pillars(body)

    assert body["source"] == "quote"
    assert pillars["price"] == {"name": "price", "passed": False, "detail": "no price data"}
    assert pillars["change_pct"]["detail"] == "no change % data"
    assert pillars["float"]["detail"] == "float unknown"
    assert body["entry"]["price"] is None
    assert body["entry"]["catalyst"] is None  # no source looked: unknown, not "no news"


def test_a_blocklisted_symbol_is_still_graded_for_the_quote_panel(desk):
    desk.gapper_cache = [{"symbol": "BLOK", "price": 5.0, "change_pct": 0.5, "volume": 10}]

    body = strategy_routes.watchlist_one("BLOK")

    assert body["source"] == "gappers"
    assert body["rank"] is None  # the ranked watchlist leaves it out, like the board
    assert _pillars(body)["price"]["passed"] is True


def test_the_quote_row_leaves_every_unknown_none():
    assert quote_row("ABC", {"price": 2.0}) == {
        "symbol": "ABC", "price": 2.0, "prev_close": None, "change_pct": None, "volume": None,
    }
    assert quote_row("ABC", {"price": float("nan"), "prev_close": 1.0, "volume": 5})["price"] is None
    assert quote_row("ABC", {"price": 3.0, "prev_close": 2.0, "volume": 5})["change_pct"] == pytest.approx(0.5)


def test_the_route_refuses_a_blank_symbol(desk):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        strategy_routes.watchlist_one("  ")
    assert err.value.status_code == 400
