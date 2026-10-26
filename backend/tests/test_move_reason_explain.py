"""The ladder behind a move read (ADR 028 amendment, the Catalyst column 2026-10-12): every cause in the rules'
order, whether it fits and why -- and the first that fits is always the likely cause."""
from __future__ import annotations

import itertools

from move_reason.fund import fact
from move_reason.rules import read
from tests.test_move_reason_rules import NONE, NOISE, NOT_LISTED, NOW, borrow, facts

CATALYST = {"verdict": "catalyst", "category": "contract_partnership", "strength": "weak", "source": "globenewswire",
            "title": "Euro Tech Holdings Company Limited Announces a 50/50 Joint Venture", "published_ts": NOW - 3600,
            "sources_answered": ["alpaca"]}
ROUTINE = {"verdict": "routine_only", "title": "Acme to Report Results on August 12", "sources_answered": ["alpaca"]}
PENDING = {"verdict": "none_found", "news_pending": True, "halt_code": "T1", "sources_answered": ["alpaca"]}
RECENT_SPLIT = {"factor": "1:9", "ts": NOW - 2 * 86400, "reverse": True, "days_ago": 2.0}
OLD_SPLIT = {"factor": "1:6", "ts": NOW - 106 * 86400, "reverse": True, "days_ago": 106.0}


def ladder(out):
    return {s["kind"]: s for s in out["likely"]["steps"]}


def first_fit(out):
    steps = out["likely"]["steps"]
    if steps[0]["fits"] is not True:
        return None
    return next(s["kind"] for s in steps[1:] if s["fits"] is True)


def test_mndr_reads_low_float_momentum_and_says_why_it_is_not_a_squeeze():
    # MNDR 2026-10-12, +204.7%: a 398K float traded 144x, nothing to lend, but 41K shares short (10% of the float).
    out = read(facts(change_pct=2.047, volume=57_200_000, float_shares=398_000, rel_volume=242.0,
                     short_interest=41_000, days_to_cover=0.3, split=OLD_SPLIT, borrow=NOT_LISTED, catalyst=NOISE), NOW)
    assert out["likely"]["kind"] == "low_float_momentum"
    steps = ladder(out)
    assert steps["move"]["fits"] is True and steps["move"]["why"] == "+204.7% today"
    # A news halt, never an LULD pause (operator report 2026-10-13: "Not halted for news" read as one).
    assert steps["news_pending"] == {"kind": "news_pending", "name": "Halted for news", "fits": False,
                                     "why": "No news halt open (T1 / T12)"}
    assert steps["news"] == {"kind": "news", "name": "Company news", "fits": False,
                             "why": "Only movers lists and market wraps"}
    squeeze = steps["short_squeeze"]
    assert squeeze["fits"] is False
    assert squeeze["why"] == ("Shorts 10% of float · 0.3 days to cover (Yahoo ratio) -- heavy is 20% of the float short, "
                              "or 3+ days to cover with 10%+ short")
    assert steps["split_squeeze"]["fits"] is False
    assert "needs one in the last 10 days" in steps["split_squeeze"]["why"]
    assert steps["low_float_momentum"] == {"kind": "low_float_momentum", "name": "Low-float momentum", "fits": True,
                                           "why": "Up +204.7%; Float 398K shares -- low float; Float traded 144x"}
    assert steps["unexplained"]["fits"] is False


def test_mss_fits_the_squeeze_with_every_part_named():
    out = read(facts(change_pct=0.487, volume=94_510_260, float_shares=300_081, rel_volume=33.6,
                     short_interest=88_477, days_to_cover=0.02, borrow=borrow(104.92, 2_000), catalyst=NONE), NOW)
    squeeze = ladder(out)["short_squeeze"]
    assert out["likely"]["kind"] == "short_squeeze" and squeeze["fits"] is True
    assert squeeze["why"].startswith("Up +48.7%; Shorts 29% of float")
    assert "Borrow: Fee 104.9%/yr · 2K shares to lend" in squeeze["why"]
    assert "Volume: float traded 315x, RVOL 34x" in squeeze["why"]


def test_unknown_short_interest_leaves_the_squeeze_unknown_not_ruled_out():
    out = read(facts(change_pct=0.6, volume=9_000_000, float_shares=2_000_000, rel_volume=12.0,
                     borrow=NOT_LISTED, catalyst=NONE), NOW)
    squeeze = ladder(out)["short_squeeze"]
    assert squeeze["fits"] is None and squeeze["why"] == "Short interest unknown"


def test_news_names_its_headline_and_a_small_move_stops_at_the_move_line():
    out = read(facts(change_pct=0.456, volume=40_700_000, float_shares=2_900_000, rel_volume=2021.0, catalyst=CATALYST),
               NOW)
    assert ladder(out)["news"]["why"] == ("Contract / partnership (weak): Euro Tech Holdings Company Limited Announces "
                                          "a 50/50 Joint Venture")
    small = read(facts(change_pct=0.013, catalyst=CATALYST), NOW)
    assert small["likely"]["kind"] == "not_moving"
    assert small["likely"]["steps"] == [{"kind": "move", "name": "A real move", "fits": False,
                                         "why": "+1.3% today -- under the 10% move line either way"}]


def test_the_first_step_that_fits_is_always_the_likely_cause():
    """Every combination of the deciding facts: the ladder and ``rules._likely`` never disagree."""
    changes = (None, 0.05, 0.6, -0.4)
    verdicts = (None, NONE, NOISE, CATALYST, ROUTINE, PENDING)
    floats = (None, 400_000, 30_000_000)
    volumes = (None, 30_000, 2_000_000, 50_000_000)
    rvols = (None, 0.5, 2.0, 40.0)
    shorts = (None, 4_000, 150_000)
    borrows = (None, NOT_LISTED, borrow(5.0, 5_000_000))
    splits = (None, {"factor": None}, RECENT_SPLIT, OLD_SPLIT)
    # Unknown, a company's shares, a fund (ADR 028 amendment 4).
    funds = ((None, None), ("EQUITY", None), ("ETF", fact("ProShares UltraShort MSCI Brazil Capped")))
    n = 0
    for change, verdict, fl, vol, rvol, si, bw, split, (qt, fd) in itertools.product(
            changes, verdicts, floats, volumes, rvols, shorts, borrows, splits, funds):
        out = read(facts(change_pct=change, catalyst=verdict, float_shares=fl, volume=vol, rel_volume=rvol,
                         short_interest=si, borrow=bw, split=split, quote_type=qt, fund=fd), NOW)
        kind = out["likely"]["kind"]
        fit = first_fit(out)
        if fit is None:
            assert kind in ("not_moving", "unexplained"), (change, kind, out["likely"]["steps"])
        else:
            assert fit == kind, (change, verdict, fl, vol, rvol, si, bw, split, kind, out["likely"]["steps"])
        n += 1
    assert n > 10_000
