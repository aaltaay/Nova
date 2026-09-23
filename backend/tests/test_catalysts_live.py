"""The live desk's catalyst verdicts (ADR 024): same window and classifier as the history."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from catalysts import live
from setup_scanner import grade as grade_mod

ET = ZoneInfo("America/New_York")
# Tuesday 2026-09-22 08:00 ET; the prior session closed Monday 2026-09-21 16:00 ET.
NOW = datetime(2026, 9, 22, 8, 0, tzinfo=ET).timestamp()
PRIOR_CLOSE = datetime(2026, 9, 21, 16, 0, tzinfo=ET).timestamp()


def art(i, headline, ts, symbols=("ACME",)):
    return {"id": i, "headline": headline, "symbols": list(symbols),
            "created_at": datetime.fromtimestamp(ts, ET).isoformat()}


@pytest.fixture(autouse=True)
def _clean():
    live.reset_for_testing()
    yield
    live.reset_for_testing()


def test_the_window_opens_at_the_prior_sessions_close():
    assert live.window_start(NOW) == PRIOR_CLOSE
    monday = datetime(2026, 9, 21, 7, 0, tzinfo=ET).timestamp()
    assert live.window_start(monday) == datetime(2026, 9, 18, 16, 0, tzinfo=ET).timestamp()  # Friday's close


def test_unknown_until_a_fetch_covers_the_window():
    assert live.verdict_for("ACME", NOW) is None
    live.record(["ACME"], [], start=PRIOR_CLOSE, through=NOW)
    assert live.verdict_for("ACME", NOW)["verdict"] == "none_found"
    # A replay playhead on another day is not covered by today's fetch: unknown, never "no news".
    assert live.verdict_for("ACME", NOW - 86400) is None


def test_a_real_catalyst_passes_and_a_movers_list_does_not():
    live.record(["ACME", "ZZZ"], [
        art(1, "12 Health Care Stocks Moving In Monday's After-Market Session", PRIOR_CLOSE + 600, ("ACME", "ZZZ")),
        art(2, "Acme Receives FDA Approval for Widget", NOW - 600),
    ], start=PRIOR_CLOSE, through=NOW)
    v = live.verdict_for("ACME", NOW)
    assert (v["verdict"], v["category"], v["strength"]) == ("catalyst", "fda_regulatory", "strong")
    assert live.verdict_for("ZZZ", NOW)["verdict"] == "noise_only"
    # Before the approval printed, only the movers list was known.
    assert live.verdict_for("ACME", NOW - 1200)["verdict"] == "noise_only"


def test_grade_reads_the_catalyst_verdict(monkeypatch):
    import hod_momo

    monkeypatch.setattr(hod_momo, "get_ticker_snapshot",
                        lambda sym: SimpleNamespace(price=4.0, change_pct=40.0, rvol=9.0, float_shares=5e6))
    live.record(["ACME"], [art(2, "Acme Receives FDA Approval for Widget", NOW - 600)], start=PRIOR_CLOSE, through=NOW)
    p = grade_mod.read_pillars("ACME", NOW)
    assert p["news"] is True and p["headline"] == "Acme Receives FDA Approval for Widget"
    assert p["catalyst"]["category"] == "fda_regulatory"
    assert grade_mod.grade(p)[0] == "A"
    # Not fetched: the pillar is unknown, never a failed "no news".
    q = grade_mod.read_pillars("OTHER", NOW)
    assert q["news"] is None and q["catalyst"] is None


def test_the_news_pillar_passes_only_a_classified_catalyst():
    assert grade_mod.news_pillar(None) is None
    assert grade_mod.news_pillar({"verdict": "catalyst", "category": "fda_regulatory"}) is True
    assert grade_mod.news_pillar({"verdict": "catalyst", "category": "company_news"}) is None
    assert grade_mod.news_pillar({"verdict": "noise_only", "news_pending": True}) is None
    assert grade_mod.news_pillar({"verdict": "none_found"}) is False
