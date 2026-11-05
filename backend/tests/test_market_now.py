"""Today's market for agents: the AI groups, the kept headlines, the agent report, and Global's old reads."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import constants_global_board as cg
from agent_desk import market_now
from global_board import board as global_board
from global_board import markets
from global_board.state import store as global_store
from market_board import themes
from market_news import feed, store


def ts(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def us():
    return markets.by_id("us")


def flow(session_date: str, read_at: float) -> dict:
    return {"basis": "future", "instrument": None, "currency": "USD", "session_date": session_date,
            "from": 0.0, "to": 1.0, "read_at": read_at, "sums": {"up": 3.0, "down": 1.0, "flat": 0.0, "traded": 4.0},
            "move": {"pct": 1.65, "last": 7721.75, "prev_close": 7596.5}}


@pytest.fixture
def global_st():
    st = global_store()
    st.reset()
    yield st
    st.reset()


def test_yesterdays_read_is_not_todays_on_an_open_market(global_st):
    now = ts("2026-11-05T15:00")                     # 10:00 ET
    global_st.put("flow:us", flow("2026-11-04", now - 64000), now - 64000)
    row = global_board.market_row(global_st, us(), now, "1D", {}, None)
    assert row["flow"]["pressure_pct"] is None and row["flow"]["error"] == global_board.WAITING_TODAY
    assert row["move"]["pct"] is None and row["move"]["error"] == global_board.WAITING_TODAY


def test_a_read_too_old_for_an_open_session_is_not_shown(global_st):
    now = ts("2026-11-05T19:00")
    read = now - cg.GLOBAL_FLOW_MAX_AGE_SEC - 1
    global_st.put("flow:us", flow("2026-11-05", read), read)
    assert global_board.market_row(global_st, us(), now, "1D", {}, None)["flow"]["pressure_pct"] is None


def test_this_sessions_read_still_shows_and_a_closed_market_keeps_its_last(global_st):
    now = ts("2026-11-05T15:00")
    global_st.put("flow:us", flow("2026-11-05", now - 60), now - 60)
    assert global_board.market_row(global_st, us(), now, "1D", {}, None)["flow"]["pressure_pct"] == 50.0
    night = ts("2026-11-06T02:00")                   # 21:00 ET, the session over
    global_st.put("flow:us", flow("2026-11-05", night - 18000), night - 18000)
    assert global_board.market_row(global_st, us(), night, "1D", {}, None)["flow"]["pressure_pct"] == 50.0


def test_a_group_averages_only_what_ibkr_priced():
    spec = {"id": "x", "label": "X", "symbols": ("AAA", "BBB", "CCC")}
    got = themes.group(spec, {"AAA": {"price": 90.0, "prev_close": 100.0}, "BBB": {"price": 110.0, "prev_close": 100.0},
                              "CCC": {"price": None, "prev_close": 100.0}})
    assert (got["change_pct"], got["priced"], got["total"]) == (0.0, 2, 3)
    assert got["rows"][2]["change_pct"] is None
    assert themes.group(spec, {})["change_pct"] is None


def article(url: str, at: str, headline: str) -> dict:
    return {"url": url, "created_at": at, "headline": headline, "summary": "", "source": "benzinga", "symbols": ["NVDA"]}


def answer(*articles, ok=True, error=None):
    return lambda: SimpleNamespace(ok=ok, error=error, articles=list(articles))


@pytest.fixture
def news_db(tmp_path):
    feed.reset_for_tests()
    db = store.connect(tmp_path / "news.sqlite3")
    yield db
    db.close()
    feed.reset_for_tests()


def test_headlines_are_kept_once_and_found_by_word(news_db):
    now = ts("2026-11-05T15:00")
    page = (article("u1", "2026-11-05T14:00:00Z", "Nvidia slides on data center rules"),
            article("u2", "2026-11-05T14:30:00Z", "Oil rises 100%"))
    feed.poll_once(now, news_db, answer(*page))
    feed.poll_once(now + 60, news_db, answer(*page))
    assert [i["url"] for i in store.search(news_db, [], now - 7200, 10)] == ["u2", "u1"]
    assert [i["url"] for i in store.search(news_db, ["data center"], now - 7200, 10)] == ["u1"]
    assert [i["url"] for i in store.search(news_db, ["1%"], now - 7200, 10)] == []     # % is a character, not a wildcard
    assert store.search(news_db, ["data center"], now - 7200, 10)[0]["symbols"] == ["NVDA"]


def test_coverage_breaks_on_a_failed_poll_and_on_a_page_that_cannot_reach_back(news_db):
    now = ts("2026-11-05T15:00")
    feed.poll_once(now, news_db, answer(article("u1", "2026-11-05T14:00:00Z", "a")))
    feed.poll_once(now + 60, news_db, answer(article("u1", "2026-11-05T14:00:00Z", "a")))
    assert len(store.spans_since(news_db, 0)) == 1
    feed.poll_once(now + 120, news_db, answer(ok=False, error="Alpaca news returned HTTP 500."))
    feed.poll_once(now + 180, news_db, answer(article("u2", "2026-11-05T15:02:30Z", "b")))
    assert len(store.spans_since(news_db, 0)) == 2


def test_the_report_names_what_it_does_not_have():
    market = {"quotes": [{"label": "VIX", "change_pct": None, "error": None}, {"label": "ES", "change_pct": -1.0}],
              "themes": {"groups": [{"label": "Memory", "priced": 1, "total": 4}]}}
    world = {"markets": [{"name": "United States", "flow": {"pressure_pct": None, "error": "waiting"}}]}
    assert market_now._missing(market, world, {"error": "no headlines kept yet"}) == [
        "VIX: no price yet", "Memory: 3 of 4 stocks not priced yet", "United States money: waiting",
        "headlines: no headlines kept yet"]
