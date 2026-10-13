"""The scanner quote panel on a Sim replay desk shows the replayed moment, never today (operator report, 2026-10-12).

Seen on the desk: Sim replaying 2026-07-15 (a Massive-rebuilt day), GRML loaded, playhead 07:20 ET. The
Pillars card graded today's GRML -- "$6.02 (need $2-$20)", "16.4%", "1.5x", "#22 of the Contenders" --
where the rebuilt board had GRML at $0.1875, #98. The News panel listed Oct 12's headlines.

Off the live edge both routes read the leaderboard store at the playhead instead: the pillars grade the
symbol's own board row (a rebuilt row's time-of-day RVOL named, never graded as the daily RVOL; its unknown
float unknown), and the News panel is the symbol-day's backfilled items published by then. Temp stores only.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import routes.strategy as strategy_routes
from catalysts import routes as catalyst_routes
from catalysts.classify import classify_item
from catalysts.windows import window_start
from constants_catalysts import CATALYST_RULES_VERSION
from leaderboard import catalyst_verdicts, store
from runtime_state import get_runtime_state
from strategy.five_pillars import evaluate_five_pillars
from strategy.replay_pillars import REPLAY_ABSENT_NOT_ON_BOARD, candidate

ET = ZoneInfo("America/New_York")
DAY = "2026-07-15"  # a Wednesday; its news window opens at Tuesday's 16:00 ET close


def et(hh: int, mm: int = 0, day: int = 15) -> float:
    return datetime(2026, 7, day, hh, mm, tzinfo=ET).timestamp()


PLAYHEAD = et(7, 20) + 26  # 07:20:26 ET, inside the 07:20 minute
WINDOW = (et(16, 0, day=14), et(20, 0))


def row(symbol: str, rank: int, **over) -> dict:
    out = {"session_date": DAY, "minute_ts": int(et(7, 20)), "source": "reconstructed", "board": "market",
           "symbol": symbol, "rank": rank, "price": 0.1875, "prev_close": 0.1801, "change_pct": 0.0411,
           "volume": 27_524.0, "rvol": 1.31, "rvol_basis": "time_of_day_20", "float_shares": None,
           "has_news": False, "exchange": "NASDAQ"}
    out.update(over)
    return out


def write_board(rows: list[dict], minute_ts: float = et(7, 20), source: str = "reconstructed",
                board: str = "market") -> None:
    coverage = [{"session_date": DAY, "minute_ts": int(minute_ts), "source": source, "board": board,
                 "state": "rebuilt" if source == "reconstructed" else "live", "row_count": len(rows),
                 "run_id": None}]
    with store.connect() as db:
        store.write_batch(db, rows=rows, coverage=coverage)


def news(symbol: str, title: str, published: float) -> dict:
    label = classify_item(title, source="alpaca")
    return {"session_date": DAY, "symbol": symbol, "item_id": f"alpaca:{symbol}:{published}",
            "published_ts": published, "source": "alpaca", "publisher": "Wire", "title": title, "url": None,
            "kind": label.kind, "category": label.category, "strength": label.strength,
            "dilution": int(label.dilution), "rules_version": CATALYST_RULES_VERSION}


def checked(symbol: str) -> dict:
    return {"session_date": DAY, "symbol": symbol, "window_start": WINDOW[0], "window_end": WINDOW[1],
            "sources_answered": "alpaca", "rules_version": CATALYST_RULES_VERSION, "exported_ts": et(21, 0)}


@pytest.fixture(autouse=True)
def own_store(monkeypatch, tmp_path):
    """Each test its own leaderboard store: the boards and backfill below never leak into another test."""
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "leaderboard"))


@pytest.fixture
def replay(monkeypatch):
    """A replay desk at 07:20:26 ET on Jul 15, with today's live GRML on the live caches and verdicts."""
    monkeypatch.setattr(strategy_routes, "_replay_playhead", lambda: PLAYHEAD)
    monkeypatch.setattr("sim.replay_playhead.replay_playhead", lambda: PLAYHEAD)

    def today(*a, **k):
        raise AssertionError("today's catalyst read on a replay desk")

    monkeypatch.setattr("catalysts.live.verdict_for", today)
    monkeypatch.setattr("catalysts.live.request", today)
    monkeypatch.setattr("catalysts.live.panel", today)
    state = get_runtime_state()
    prev = state.gainer_cache
    state.gainer_cache = [{"symbol": "GRML", "price": 6.02, "change_pct": 0.164, "volume": 11_746_344}]
    yield
    state.gainer_cache = prev


def _pillars(body: dict) -> dict[str, dict]:
    return {p["name"]: p for p in body["entry"]["five_pillars"]["pillars"]}


# ── The Pillars card ────────────────────────────────────────────────────────

def test_a_replay_desk_grades_the_replayed_days_own_row(replay):
    write_board([row("KUST", 1, price=1.55, prev_close=1.01, change_pct=0.53), row("GRML", 98)])

    body = strategy_routes.watchlist_one("grml")

    assert (body["symbol"], body["source"], body["rank"]) == ("GRML", "replay", None)
    pillars = _pillars(body)
    assert pillars["price"] == {"name": "price", "passed": False, "detail": "$0.19 (need $2-$20)"}
    assert pillars["change_pct"]["detail"].startswith("4.1%")
    assert pillars["float"]["detail"] == "float unknown"
    assert body["entry"]["price"] == 0.1875 and body["entry"]["float_shares"] is None
    assert body["entry"]["catalyst"] is None  # not in the day's backfill: unknown, never today's verdict
    assert body["replay"] == {
        "session_date": DAY, "at": PLAYHEAD, "minute_ts": int(et(7, 20)), "board_source": "reconstructed",
        "board": "market", "board_rank": 98, "rvol": 1.31, "rvol_basis": "time_of_day_20", "absent": None,
    }


def test_a_time_of_day_rvol_is_named_and_never_graded_as_the_daily_rvol(replay):
    write_board([row("GRML", 98, rvol=9.0)])  # 9x would pass a 5x daily threshold

    body = strategy_routes.watchlist_one("GRML")

    rvol = _pillars(body)["relative_volume"]
    assert rvol["passed"] is False
    assert rvol["detail"] == ("daily RVOL unknown -- 9.0x the same minute's 20-day average is another measure, "
                              "not graded")
    assert body["entry"]["rel_volume"] is None
    assert body["entry"]["sub_scores"]["relative_volume"] == 0.0


def test_a_recorded_days_daily_rvol_and_float_are_graded(replay):
    write_board([row("GRML", 2, source="recorded", board="gainers", price=6.5, change_pct=0.42, rvol=7.0,
                     rvol_basis="daily_avg", float_shares=3_000_000.0)],
                source="recorded", board="gainers")
    with store.connect() as db:
        store.write_batch(db, minutes=[{"session_date": DAY, "minute_ts": int(et(7, 20)), "run_id": "run-1",
                                        "feed_live": 1, "halt_feed_ok": 1}])

    body = strategy_routes.watchlist_one("GRML")

    pillars = _pillars(body)
    assert pillars["relative_volume"] == {"name": "relative_volume", "passed": True, "detail": "7.0x (need >= 5x)"}
    assert pillars["float"]["passed"] is True
    assert body["replay"]["board"] == "gainers" and body["replay"]["board_source"] == "recorded"


def test_a_symbol_not_on_the_replayed_board_has_no_grade_and_says_why(replay):
    write_board([row("KUST", 1)])

    body = strategy_routes.watchlist_one("GRML")

    assert body["entry"] is None and body["source"] == "replay"
    assert body["replay"]["absent"] == REPLAY_ABSENT_NOT_ON_BOARD
    assert body["replay"]["board"] is None and body["replay"]["board_rank"] is None


def test_no_board_at_the_playhead_names_the_gap(replay, monkeypatch):
    monkeypatch.setattr(strategy_routes, "_replay_playhead", lambda: et(3, 30))  # before the 04:00 session

    body = strategy_routes.watchlist_one("GRML")

    assert body["entry"] is None
    assert body["replay"]["absent"] == "outside_session"


def test_the_candidate_keeps_a_daily_rvol_and_drops_nothing_else():
    daily = candidate(row("GRML", 1, rvol=6.0, rvol_basis="daily_avg"))
    tod = candidate(row("GRML", 1))

    assert (daily["rel_volume"], daily["rvol_time_of_day"]) == (6.0, None)
    assert (tod["rel_volume"], tod["rvol_time_of_day"]) == (None, 1.31)
    assert evaluate_five_pillars({"symbol": "X"}).checks[2].detail == "no relative volume data"


# ── The News panel ──────────────────────────────────────────────────────────

def test_the_news_panel_is_the_replayed_days_items_by_the_playhead(replay):
    with store.connect() as db:
        store.replace_catalysts(db, [checked("ACME")], [
            news("ACME", "Acme Receives FDA Approval for Its Lead Drug", et(7, 5)),
            news("ACME", "Acme Announces $5 Million Registered Direct Offering", et(9, 30)),  # after the playhead
            news("ACME", "Acme Reports Results", et(15, 0, day=14)),  # before the window opened
        ])

    body = catalyst_routes.catalyst_panel("acme")

    assert body["replay"] == {"session_date": DAY, "at": PLAYHEAD, "on_file": True}
    assert body["generated_at"] == PLAYHEAD and body["window_start"] == WINDOW[0]
    assert [i["title"] for i in body["items"]] == ["Acme Receives FDA Approval for Its Lead Drug"]
    assert body["items_total"] == 1
    assert body["verdict"]["verdict"] == "catalyst"
    assert body["verdict"]["negative_too"] is False  # the offering came after the playhead


def test_a_symbol_the_days_backfill_does_not_hold_is_unknown_never_todays_news(replay):
    body = catalyst_routes.catalyst_panel("GRML")

    assert body["verdict"] is None and body["items"] == [] and body["items_total"] == 0
    assert body["replay"] == {"session_date": DAY, "at": PLAYHEAD, "on_file": False}
    assert body["window_start"] == window_start(PLAYHEAD)


def test_the_live_news_panel_says_it_is_not_a_replay(monkeypatch):
    monkeypatch.setattr("sim.replay_playhead.replay_playhead", lambda: None)
    monkeypatch.setattr("catalysts.live.panel", lambda symbol: {"symbol": symbol, "items": [], "verdict": None})

    assert catalyst_routes.catalyst_panel("GRML") == {"symbol": "GRML", "items": [], "verdict": None,
                                                      "replay": None}


def test_panel_at_reads_only_its_own_symbol():
    with store.connect() as db:
        store.replace_catalysts(db, [checked("SOLO"), checked("OTHR")], [
            news("OTHR", "Othr Receives FDA Approval for Its Lead Drug", et(7, 0)),
        ])

    body = catalyst_verdicts.panel_at("solo", DAY, PLAYHEAD)

    assert body["items"] == [] and body["replay"]["on_file"] is True
    assert body["verdict"]["verdict"] == "none_found"


# ── The replay playhead ─────────────────────────────────────────────────────

def test_replay_playhead_is_none_on_a_live_desk_and_the_playhead_off_the_edge(monkeypatch):
    from sim import mode, replay_playhead as rp, session_clock

    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    assert rp.replay_playhead() is None

    # The Sim clock is held still: two reads of a running clock differ by microseconds (CI on PR #894).
    playhead = datetime(2026, 7, 15, 7, 20, tzinfo=ET)
    monkeypatch.setattr(session_clock, "now_et", lambda: playhead)
    monkeypatch.setattr(mode, "is_replay_desk", lambda: True)
    assert rp.replay_playhead() == playhead.timestamp()


def test_an_unreadable_live_edge_counts_as_a_replay(monkeypatch):
    from sim import mode, replay_playhead as rp

    def broken():
        raise RuntimeError("clock unreadable")

    monkeypatch.setattr(mode, "is_replay_desk", broken)
    assert rp.replay_playhead() is not None
