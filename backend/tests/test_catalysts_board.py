"""The catalyst verdict on the desk (ADR 024 amendment): scanner rows, the Trader's News panel, the pillars."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from catalysts import board, live
from catalysts.routes import router
from strategy.five_pillars import evaluate_five_pillars
from strategy.watchlist import score_watchlist_entry

ET = ZoneInfo("America/New_York")
# Wednesday 2026-09-23 10:00 ET; the prior session closed Tuesday 2026-09-22 16:00 ET.
NOW = datetime(2026, 9, 23, 10, 0, tzinfo=ET).timestamp()
PRIOR_CLOSE = datetime(2026, 9, 22, 16, 0, tzinfo=ET).timestamp()
WRAP = "Dow Falls 100 Points; General Mills Posts Upbeat Q1 Earnings"


def art(i, headline, ts, symbols=("BENF",)):
    return {"id": i, "headline": headline, "symbols": list(symbols),
            "created_at": datetime.fromtimestamp(ts, ET).isoformat(), "url": f"https://example.test/{i}"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    live.reset_for_testing()
    board.reset_for_testing()
    monkeypatch.setattr(live, "_feed_view", lambda *a: ([], []))
    monkeypatch.setattr(live, "_drain", lambda: None)  # request queues; nothing reads Alpaca
    yield
    live.reset_for_testing()
    board.reset_for_testing()


def _today():
    live.record(["BENF", "WHLR", "HCTI"], [
        art(1, WRAP, NOW - 600, ("BENF", "WHLR", "IPDN", "GIS", "A", "B", "C")),
        art(2, "Beneficient Announces Strategy to Eliminate HCLP Debt and Heppner Equity Interests", NOW - 9000),
        art(3, "Healthcare Triangle Signs Letter of Intent to Pursue the Proposed Acquisition of Roboticom",
            NOW - 2400, ("HCTI",)),
    ], start=PRIOR_CLOSE, through=NOW)


def test_a_scanner_row_carries_the_verdict_not_the_market_wrap():
    _today()
    board.refresh({"BENF", "WHLR", "HCTI", "TNMG"}, NOW)
    rows = {s: {"symbol": s} for s in ("BENF", "WHLR", "HCTI", "TNMG", "NEW")}
    for row in rows.values():
        board.stamp_row(row)
    assert (rows["BENF"]["catalyst"]["verdict"], rows["BENF"]["catalyst"]["category"]) == (
        "catalyst", "listing_financing")
    assert rows["WHLR"]["catalyst"]["verdict"] == "noise_only"          # only the Dow wrap named it
    assert rows["HCTI"]["catalyst"]["category"] == "merger_acquisition"
    assert rows["TNMG"]["catalyst"] is None                             # never read: unknown, not "no news"
    assert rows["NEW"]["catalyst"] is None                              # not on a board yet
    assert set(rows["BENF"]["catalyst"]) == set(live.WIRE_KEYS)


def test_the_panel_lists_every_item_labelled_newest_first():
    _today()
    out = live.panel("benf", NOW)
    assert out["symbol"] == "BENF" and out["schema_version"] == 1 and out["window_start"] == PRIOR_CLOSE
    assert [(i["kind"], i["category"]) for i in out["items"]] == [
        ("noise", "movers_list"), ("catalyst", "listing_financing")]
    assert out["verdict"]["verdict"] == "catalyst" and out["items_total"] == 2
    assert out["verdict"]["sources_answered"] == ["alpaca"]


def test_the_panel_reads_a_symbol_no_board_carries(monkeypatch):
    calls = []

    def fake_fetch(symbols, headers):
        calls.append(list(symbols))
        live.record(symbols, [], start=PRIOR_CLOSE, through=NOW)

    monkeypatch.setattr(live, "_fetch", fake_fetch)
    monkeypatch.setattr("alpaca._alpaca_headers", lambda: {"k": "v"})
    out = live.panel("ZZZZ", NOW)
    assert calls == [["ZZZZ"]]
    assert out["verdict"]["verdict"] == "none_found" and out["items"] == []
    live.panel("ZZZZ", NOW)
    assert calls == [["ZZZZ"]]  # fresh: read once


def test_an_earlier_sessions_reads_are_dropped():
    live.record(["OLD"], [], start=PRIOR_CLOSE - 86400, through=PRIOR_CLOSE - 3600)
    live.request([])
    assert live.verdict_for("OLD", NOW) is None
    assert "OLD" not in live._fetched


def test_the_route_answers_the_panel(monkeypatch):
    monkeypatch.setattr(live, "panel", lambda sym: {"symbol": sym, "items": []})
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/catalysts/brk/b").json()["symbol"] == "BRK/B"
    assert client.get("/api/catalysts/" + "X" * 20).status_code == 400


def _candidate(**kw):
    base = {"symbol": "MOCK", "price": 5.0, "change_pct": 15.0, "rel_volume": 6.0, "has_news": True,
            "float": 8_000_000}
    base.update(kw)
    return base


def test_the_catalyst_pillar_reads_the_verdict_when_one_was_read():
    wrap = {"verdict": "noise_only", "category": "movers_list", "title": WRAP}
    check = {c.name: c for c in evaluate_five_pillars(_candidate(catalyst=wrap)).checks}["catalyst"]
    assert (check.passed, check.detail) == (False, "only movers lists and market wraps -- no company news")
    real = {"verdict": "catalyst", "category": "merger_acquisition", "title": "Acme to Acquire Widget Co",
            "published_ts": NOW}
    check = {c.name: c for c in evaluate_five_pillars(_candidate(catalyst=real)).checks}["catalyst"]
    assert check.passed and check.detail.startswith("catalyst: merger acquisition")
    # Not read yet: the article-exists answer stands, as before.
    unread = {c.name: c for c in evaluate_five_pillars(_candidate(catalyst=None)).checks}["catalyst"]
    assert unread.passed and unread.detail == "news catalyst present"


def test_the_watchlist_scores_a_market_wrap_as_no_catalyst():
    wrap = {"verdict": "noise_only", "category": "movers_list", "title": WRAP}
    assert score_watchlist_entry(_candidate(catalyst=wrap)).sub_scores["catalyst"] == 0.0
    assert score_watchlist_entry(_candidate(catalyst=None)).sub_scores["catalyst"] == 100.0
