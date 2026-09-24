"""GET /api/why/{symbol} (ADR 028): the facts gathered from the desk's own caches, then the read."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import scanner_news_badge as snb
import scanner_surface
from fundamentals import _fundamentals_cache
from leaderboard import store as lb_store
from move_reason import borrow_feed, borrow_store, facts as facts_mod, routes
from runtime_state import get_runtime_state

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 23, 11, 0, tzinfo=ET).timestamp()
BOARDS = ("gapper_cache", "gainer_cache", "loser_cache", "afterhours_cache", "large_cap_cache")
USA_TXT = ("#BOF|2026.09.23|10:45:00\n#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI|\n"
           "MSS|USD|MAISON|1|X|-101.04|104.92|2000|F|\n#EOF|1\n").encode()


@pytest.fixture
def desk(monkeypatch, tmp_path):
    monkeypatch.setattr("alpaca._get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scanner_surface._hod_momo, "is_blocked", lambda s: False)
    monkeypatch.setattr("catalysts.live.request", lambda symbols: None)
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: {
        "verdict": "none_found", "sources_answered": ["alpaca", "finnhub"], "news_pending": False})
    monkeypatch.setattr("strategy.symbol_pillars.live_quote", lambda symbol: None)
    monkeypatch.setattr(facts_mod, "_read_in_background", lambda sym: None)
    monkeypatch.setenv("NOVA_BORROW_FEED", "1")
    feed = borrow_feed.BorrowFeed(fetch=lambda: USA_TXT, clock=lambda: NOW - 900,
                                  db=borrow_store.connect(tmp_path / "borrow.sqlite3"))
    feed.warm_start()
    assert feed.poll_once()
    monkeypatch.setattr(borrow_feed, "_feed", feed)
    snb.reset_for_testing()
    state = get_runtime_state()
    prev = {name: getattr(state, name) for name in BOARDS}
    for name in BOARDS:
        setattr(state, name, [])
    yield state
    for name, rows in prev.items():
        setattr(state, name, rows)
    snb.reset_for_testing()


def halts(*events):
    with lb_store.connect() as db:
        lb_store.write_batch(db, halts=[{"symbol": s, "ts": ts, "event": "start", "kind": k, "code": c, "source": src,
                                         "session_date": "2026-09-23", "recorded_ts": ts} for s, ts, k, c, src in events])


def test_a_gainer_squeezing_without_news_says_so(desk, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "MSS", {
        "average_volume": 2_800_000.0, "float_shares": 300_081, "short_interest": 88_477, "short_ratio": 0.02,
        "last_split_factor": None, "last_split_ts": None})
    desk.gainer_cache = [{"symbol": "MSS", "price": 2.32, "change_pct": 0.487, "volume": 94_510_260}]
    halts(("MSS", NOW - 3600, "LUDP", "LUDP", "nasdaq_trade_halt_rss"),
          ("MSS", NOW - 3599, "luld", "2", "ibkr_ticker_halted"),       # the same pause seen by IBKR
          ("MSS", NOW - 1800, "LUDP", "LUDP", "nasdaq_trade_halt_rss"))

    body = routes.why("mss", NOW)

    assert (body["schema_version"], body["symbol"], body["session_date"]) == (1, "MSS", "2026-09-23")
    assert body["likely"]["kind"] == "short_squeeze"
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["halts"]["value"] == "LULD pause 2x"
    assert checks["borrow"]["value"] == "Fee 104.9%/yr · 2K shares to lend"
    assert checks["reverse_split"]["value"] == "None on record"
    assert body["facts"]["float_rotation"] == pytest.approx(94_510_260 / 300_081)
    assert body["facts"]["borrow"]["open"]["fee_rate"] == 104.92


def test_a_symbol_on_no_board_with_nothing_cached_is_all_unknown(desk, monkeypatch):
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: None)
    body = routes.why("ZZZZ", NOW)
    checks = {c["id"]: c["state"] for c in body["checks"]}
    assert checks["news"] == checks["float"] == checks["short_interest"] == checks["reverse_split"] == "unknown"
    assert checks["borrow"] == "yes"          # the file was read, and it does not list ZZZZ: nothing to lend
    assert checks["halts"] == "no"
    assert body["likely"]["kind"] == "unexplained" and body["likely"]["confidence"] == "possible"


def test_a_failed_yahoo_read_is_unknown_not_no_split(desk, monkeypatch):
    import fundamentals

    monkeypatch.setitem(_fundamentals_cache, "FAIL", dict(fundamentals._EMPTY))
    monkeypatch.setattr(fundamentals, "fetch_failed", lambda s: s == "FAIL")
    desk.gainer_cache = [{"symbol": "FAIL", "price": 1.0, "change_pct": 0.4, "volume": 1_000}]
    checks = {c["id"]: c["state"] for c in routes.why("FAIL", NOW)["checks"]}
    assert checks["reverse_split"] == "unknown"


def test_a_stale_float_and_its_short_interest_date_reach_the_read(desk, monkeypatch):
    """#532: SECZ's 8.45M float against 163.27M shares out (12.8% insiders) is flagged on its surfaced row,
    and the short-interest check is as of FINRA's settlement date."""
    import fundamentals

    aug_31 = datetime(2026, 8, 31, tzinfo=ZoneInfo("UTC")).timestamp()
    flag, reason = fundamentals.float_credibility(8_450_000, 163_270_000, 0.128, 3_760_000)
    monkeypatch.setitem(_fundamentals_cache, "SECZ", {
        "float_shares": 8_450_000, "shares_outstanding": 163_270_000, "held_percent_insiders": 0.128,
        "short_interest": 3_760_000, "short_interest_ts": int(aug_31), "short_ratio": 1.4,
        "float_contradicted": flag, "float_contradicted_reason": reason})
    desk.gainer_cache = [{"symbol": "SECZ", "price": 11.2, "change_pct": 0.62, "volume": 30_000_000}]

    body = routes.why("SECZ", NOW)

    assert body["facts"]["float_contradicted"] is True
    assert body["facts"]["short_interest_ts"] == aug_31
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["float"]["value"] == "8.4M? shares -- low float"
    assert checks["float"]["detail"].startswith("Float 8.45M is under half of the 142.37M shares not held by insiders")
    assert checks["short_interest"]["as_of"] == aug_31


def test_the_borrow_feed_off_reads_unknown(desk, monkeypatch):
    monkeypatch.setenv("NOVA_BORROW_FEED", "0")
    checks = {c["id"]: c for c in routes.why("MSS", NOW)["checks"]}
    assert checks["borrow"]["state"] == "unknown"


def test_halts_count_one_source():
    events = [{"source": "ibkr_ticker_halted", "event": "start", "kind": "luld", "code": "2"},
              {"source": "ibkr_ticker_halted", "event": "start", "kind": "halt", "code": "T1"}]
    assert facts_mod.count_halts(events) == {"news": 1, "luld": 1, "volatility": 0, "other": 0,
                                             "source": "ibkr_ticker_halted"}
    assert facts_mod.count_halts([]) == {"news": 0, "luld": 0, "volatility": 0, "other": 0, "source": None}
