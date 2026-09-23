"""Finnhub company news in the live catalyst verdict (ADR 024 amendment, 2026-09-23)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import finnhub_http
from catalysts import live, live_finnhub
from constants_catalysts import CATALYST_FINNHUB_TTL_SEC

ET = ZoneInfo("America/New_York")
# Wednesday 2026-09-23 09:30 ET; the prior session closed Tuesday 2026-09-22 16:00 ET.
NOW = datetime(2026, 9, 23, 9, 30, tzinfo=ET).timestamp()
PRIOR_CLOSE = datetime(2026, 9, 22, 16, 0, tzinfo=ET).timestamp()


def fh(i, headline, ts, source="Yahoo", summary=""):
    return {"id": i, "headline": headline, "datetime": int(ts), "source": source, "summary": summary,
            "url": f"https://finnhub.io/api/news?id={i}"}


@pytest.fixture(autouse=True)
def _clean():
    live.reset_for_testing()
    finnhub_http.reset_for_testing()
    yield
    live.reset_for_testing()
    finnhub_http.reset_for_testing()


def test_a_release_only_finnhub_carried_decides_the_verdict():
    # DCOY 2026-09-22: Alpaca had only movers lists; the correction went out on PR Newswire at 18:14 ET,
    # before the wire feed was running. Finnhub's Yahoo copy carried it.
    live.record(["DCOY"], [{"id": 1, "headline": "12 Health Care Stocks Moving In Tuesday's After-Market Session",
                            "symbols": ["DCOY"] + [f"X{i}" for i in range(11)],
                            "created_at": datetime.fromtimestamp(PRIOR_CLOSE + 3900, ET).isoformat()}],
                start=PRIOR_CLOSE, through=NOW)
    assert live.verdict_for("DCOY", NOW)["verdict"] == "noise_only"
    live_finnhub.record("DCOY", [fh(7, "Decoy Therapeutics, Inc. Issues Correction to Warrant Inducement Transaction "
                                       "Press Release", PRIOR_CLOSE + 2 * 3600 + 840)], start=PRIOR_CLOSE, through=NOW)
    v = live.verdict_for("DCOY", NOW)
    assert (v["verdict"], v["category"], v["source"]) == ("negative", "offering_dilution", "finnhub")
    assert v["sources_answered"] == ["alpaca", "finnhub"]


def test_finnhubs_benzinga_copies_are_dropped_for_their_clock():
    # #516: Finnhub stamps Benzinga items with Eastern time read as UTC -- four hours early.
    live_finnhub.record("BENF", [
        fh(1, "Beneficient Implements Strategy To Eliminate HCLP Indebtedness", NOW - 6 * 3600, source="Benzinga"),
        fh(2, "Beneficient Announces Strategy to Eliminate HCLP Debt and Heppner Equity Interests", NOW - 7200),
    ], start=PRIOR_CLOSE, through=NOW)
    items, answered = live_finnhub.gather("BENF", PRIOR_CLOSE, NOW)
    assert answered and [it["publisher"] for it in items] == ["Yahoo"]


def test_a_read_counts_as_looked_only_while_it_is_young():
    assert live_finnhub.gather("ACME", PRIOR_CLOSE, NOW) == ([], False)
    live_finnhub.record("ACME", [], start=PRIOR_CLOSE, through=NOW)
    assert live_finnhub.gather("ACME", PRIOR_CLOSE, NOW)[1] is True
    assert live.verdict_for("ACME", NOW)["verdict"] == "none_found"
    later = NOW + CATALYST_FINNHUB_TTL_SEC + 1
    assert live_finnhub.gather("ACME", PRIOR_CLOSE, later)[1] is False
    # A read that began after the window opened never answers for it.
    live_finnhub.record("LATE", [], start=PRIOR_CLOSE + 60, through=NOW)
    assert live_finnhub.gather("LATE", PRIOR_CLOSE, NOW)[1] is False


def test_the_queue_reads_symbols_never_read_before_the_oldest_read(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    started = []
    monkeypatch.setattr(live_finnhub.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: started.append(kw["name"]),
                                                    "is_alive": lambda self: True})())
    live_finnhub.record("OLD", [], start=PRIOR_CLOSE, through=NOW - CATALYST_FINNHUB_TTL_SEC)
    live_finnhub.record("FRESH", [], start=PRIOR_CLOSE, through=NOW)
    live_finnhub.request({"OLD", "FRESH", "NEW"}, PRIOR_CLOSE, NOW)
    assert started == ["catalysts_finnhub"]
    with live_finnhub._lock:
        assert live_finnhub._pending == {"OLD", "NEW"}   # FRESH is young enough
        assert live_finnhub._next_symbol() == "NEW"
        assert live_finnhub._next_symbol() == "OLD"


def test_no_key_queues_nothing(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    live_finnhub.request({"ACME"}, PRIOR_CLOSE, NOW)
    assert live_finnhub.status()["pending"] == 0 and live_finnhub.status()["enabled"] is False


def test_a_429_sets_the_shared_cooldown_and_keeps_the_symbol(monkeypatch):
    class Resp:
        status_code = 429
        headers = {"Retry-After": "30"}

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **kw: Resp())
    live_finnhub._read("ACME", "test-key", PRIOR_CLOSE)
    assert finnhub_http.is_blocked()
    assert live_finnhub.status()["pending"] == 1
    assert live_finnhub.gather("ACME", PRIOR_CLOSE, NOW)[1] is False


def test_the_news_panel_lists_one_release_once(monkeypatch):
    monkeypatch.setattr(live, "ensure", lambda symbols, now=None: None)
    monkeypatch.setattr(live_finnhub, "ensure", lambda symbol, start, now=None: None)
    title = "Artelo Biosciences Files New Provisional Patent Application Covering ART27.13 for Obesity"
    monkeypatch.setattr(live, "_feed_view", lambda sym, start, now: (
        [{"item_id": "globenewswire:x", "source": "globenewswire", "published_ts": NOW - 7000, "title": title,
          "url": "https://www.globenewswire.com/x", "publisher": "GlobeNewswire"}], ["globenewswire"]))
    live_finnhub.record("ARTL", [fh(3, title, NOW - 7000)], start=PRIOR_CLOSE, through=NOW)
    out = live.panel("ARTL", NOW)
    assert [it["source"] for it in out["items"]] == ["globenewswire"]


def test_a_refused_symbol_waits_before_it_is_read_again(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(live_finnhub.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: None, "is_alive": lambda self: True})())
    live_finnhub._note_error("HVIIU", RuntimeError("403 Forbidden"))
    live_finnhub.request({"HVIIU"}, PRIOR_CLOSE)
    assert live_finnhub.status()["pending"] == 0
    assert live_finnhub.gather("HVIIU", PRIOR_CLOSE, NOW)[1] is False  # refused is not "looked"
