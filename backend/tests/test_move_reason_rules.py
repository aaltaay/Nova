"""Why it's moving (ADR 028): the rules on the 2026-09-23 movers, whose causes were checked by hand."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from move_reason.rules import read

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 23, 17, 30, tzinfo=ET).timestamp()
NONE = {"verdict": "none_found", "sources_answered": ["alpaca", "finnhub"]}
NOISE = {"verdict": "noise_only", "sources_answered": ["alpaca"]}
NOT_LISTED = {"listed": False, "fee_rate": None, "available": None, "available_capped": False, "as_of": NOW,
              "open": None}
NO_HALTS = {"news": 0, "luld": 0, "volatility": 0, "other": 0}
NO_SPLIT = {"factor": None}


def borrow(fee, available, open_fee=None, open_available=None):
    opened = None if open_fee is None else {"listed": True, "fee_rate": open_fee, "available": open_available}
    return {"listed": True, "fee_rate": fee, "available": available, "available_capped": False, "as_of": NOW,
            "open": opened}


def facts(**kw):
    base = {"change_pct": 0.5, "volume": None, "rel_volume": None, "float_shares": None, "short_interest": None,
            "short_pct_float": None, "days_to_cover": None, "split": NO_SPLIT, "halts": NO_HALTS, "borrow": None,
            "catalyst": NONE}
    return {**base, **kw}


def by_id(out):
    return {c["id"]: c for c in out["checks"]}


def test_mss_is_a_short_squeeze_without_news():
    # +49%, 300K float traded 315x, 29% of it short, IBKR lending 2,000 shares at 105% a year.
    out = read(facts(change_pct=0.487, volume=94_510_260, float_shares=300_081, rel_volume=33.6,
                     short_interest=88_477, days_to_cover=0.02, borrow=borrow(104.92, 2_000), catalyst=NONE), NOW)
    assert out["likely"]["kind"] == "short_squeeze"
    assert out["likely"]["label"] == "Likely short squeeze -- no company news"
    assert out["likely"]["confidence"] == "likely"
    checks = by_id(out)
    assert checks["short_interest"]["value"].startswith("29% of float")
    assert checks["borrow"]["state"] == "yes" and checks["borrow"]["value"] == "Fee 104.9%/yr · 2K shares to lend"


def test_whlr_squeezes_after_its_reverse_split_with_nothing_to_lend():
    split = {"factor": "1:9", "ts": NOW - 1.5 * 86400, "reverse": True, "days_ago": 1.5}
    out = read(facts(change_pct=1.909, volume=90_962_609, float_shares=53_650, rel_volume=261.9, short_interest=62_893,
                     days_to_cover=0.2, split=split, borrow=NOT_LISTED, catalyst=NOISE), NOW)
    assert out["likely"]["label"] == "Likely short squeeze after a 1-for-9 reverse split -- no company news"
    assert by_id(out)["borrow"]["value"] == "Nothing to lend"
    assert by_id(out)["reverse_split"]["value"] == "1-for-9, 2 days ago"


def test_a_tight_borrow_without_heavy_shorts_is_low_float_momentum_not_a_squeeze():
    # VSA +84%: 620K float traded 24x, nothing to lend, but only 1.5% of the float short.
    out = read(facts(change_pct=0.838, volume=14_843_599, float_shares=620_668, rel_volume=80.9, short_interest=9_496,
                     days_to_cover=0.05, borrow=NOT_LISTED, catalyst=NOISE), NOW)
    assert out["likely"]["kind"] == "low_float_momentum"
    assert out["likely"]["label"] == "Low-float momentum -- no company news; borrow is tight"


def test_a_routine_company_item_on_a_low_float_is_named():
    artl = {"verdict": "routine_only", "title": "Artelo Biosciences Files Provisional Patent Application For ART27.13",
            "source": "alpaca", "sources_answered": ["alpaca"]}
    out = read(facts(change_pct=0.745, volume=23_756_865, float_shares=510_211, rel_volume=373.6, catalyst=artl), NOW)
    assert out["likely"]["kind"] == "routine_news"
    assert out["likely"]["label"] == "Routine company item on a low float"
    assert out["likely"]["detail"].startswith("Artelo Biosciences Files")


def test_company_news_leads_and_names_its_class():
    bfrg = {"verdict": "catalyst", "category": "listing_financing", "strength": "weak", "source": "alpaca",
            "title": "BullFrog AI Holdings Stock Climbs Over 24% Pre-Market", "sources_answered": ["alpaca"]}
    out = read(facts(change_pct=0.55, volume=187_193_969, float_shares=16_106_020, catalyst=bfrg), NOW)
    assert out["likely"]["kind"] == "news"
    assert out["likely"]["label"] == "Company news: listing / financing (weak)"


def test_a_news_halt_comes_first():
    v = {"verdict": "none_found", "news_pending": True, "halt_code": "T1", "sources_answered": ["alpaca"]}
    out = read(facts(change_pct=0.4, catalyst=v), NOW)
    assert out["likely"]["kind"] == "news_pending"
    assert by_id(out)["news"]["value"] == "Halted for news (T1)"


def test_thin_trading_is_below_the_usual_volume_not_a_big_float():
    # TJGC +38% on 384K shares, a third of its usual volume.
    tjgc = read(facts(change_pct=0.383, volume=383_688, float_shares=5_873_365, rel_volume=0.34), NOW)
    assert tjgc["likely"]["kind"] == "thin_trading"
    # TLSA +18% traded 3% of a 62M float on 2.4x its usual volume: not thin, and nothing explains it.
    tlsa = read(facts(change_pct=0.18, volume=1_538_568, float_shares=61_886_576, rel_volume=2.42,
                      borrow=borrow(1.31, 1_500_000)), NOW)
    assert tlsa["likely"]["kind"] == "unexplained"
    assert by_id(tlsa)["borrow"]["state"] == "no"


def test_a_squeeze_is_never_called_without_borrow_data():
    out = read(facts(change_pct=0.487, volume=94_510_260, float_shares=300_081, rel_volume=33.6,
                     short_interest=88_477, borrow=None), NOW)
    assert out["likely"]["kind"] == "low_float_momentum"
    assert by_id(out)["borrow"]["state"] == "unknown"


def test_the_borrow_market_turning_since_the_open_counts():
    b = borrow(45.0, 20_000, open_fee=20.0, open_available=500_000)
    check = by_id(read(facts(borrow=b), NOW))["borrow"]
    assert check["state"] == "yes"
    assert check["detail"] == "fee 20% -> 45% since the open; lendable 500K -> 20K since the open"


def test_unknown_news_says_possible_and_small_moves_are_not_read():
    out = read(facts(change_pct=0.9, volume=5_000_000, float_shares=1_000_000, catalyst=None), NOW)
    assert out["likely"]["confidence"] == "possible"
    assert out["likely"]["label"].endswith("news not read yet")
    assert by_id(out)["news"]["state"] == "unknown"
    flat = read(facts(change_pct=0.032), NOW)
    assert (flat["likely"]["kind"], flat["likely"]["label"]) == ("not_moving", "Not a big move today (+3.2%)")


@pytest.mark.parametrize("split,state", [
    (None, "unknown"),
    (NO_SPLIT, "no"),
    ({"factor": "2:1", "ts": NOW - 86400, "reverse": False, "days_ago": 1.0}, "no"),
    ({"factor": "1:9", "ts": NOW - 40 * 86400, "reverse": True, "days_ago": 40.0}, "no"),
    ({"factor": "1:9", "ts": NOW - 3 * 86400, "reverse": True, "days_ago": 3.0}, "yes"),
])
def test_a_reverse_split_counts_only_when_recent(split, state):
    assert by_id(read(facts(split=split), NOW))["reverse_split"]["state"] == state


def test_every_unknown_is_stated():
    out = read({"change_pct": 0.3}, NOW)
    states = {c["id"]: c["state"] for c in out["checks"]}
    assert set(states.values()) == {"unknown"}
    assert out["likely"]["kind"] == "unexplained" and out["likely"]["confidence"] == "possible"
    assert out["likely"]["detail"].startswith("Unknown: company news, halts today, float")


def test_the_days_first_borrow_reading_is_named_by_its_time_and_only_when_it_differs():
    nine = datetime(2026, 9, 23, 9, 25, tzinfo=ET).timestamp()
    b = borrow(45.0, 20_000, open_fee=20.0, open_available=500_000)
    b["open"]["as_of"] = nine
    assert by_id(read(facts(borrow=b), NOW))["borrow"]["detail"] == (
        "fee 20% -> 45% since 09:25 ET; lendable 500K -> 20K since 09:25 ET")
    same = borrow(1.3, 1_500_000, open_fee=1.3, open_available=1_500_000)
    assert by_id(read(facts(borrow=same), NOW))["borrow"]["detail"] is None
    gone = {**NOT_LISTED, "open": {"listed": True, "fee_rate": 30.0, "available": 50_000, "as_of": nine}}
    assert by_id(read(facts(borrow=gone), NOW))["borrow"]["detail"] == "Since 09:25 ET it had fee 30.0%/yr · 50K shares to lend"


def test_a_tiny_days_to_cover_is_said_plainly():
    check = by_id(read(facts(float_shares=300_081, short_interest=88_477, days_to_cover=0.02), NOW))["short_interest"]
    assert check["value"] == "29% of float · under 0.1 days to cover (Yahoo ratio)"


# FINRA's 2026-08-31 settlement, as Yahoo stamps it (midnight UTC).
AUG_31 = datetime(2026, 8, 31, tzinfo=ZoneInfo("UTC")).timestamp()


def test_short_interest_carries_its_settlement_date_and_names_yahoos_ratio():
    """#532: the short-interest check is as of FINRA's settlement, and days to cover is Yahoo's own ratio."""
    check = by_id(read(facts(float_shares=300_081, short_interest=88_477, days_to_cover=6.9,
                             short_interest_ts=AUG_31), NOW))["short_interest"]
    assert check["as_of"] == AUG_31
    assert check["detail"] == "88K shares short, FINRA settlement Aug 31"
    assert check["value"] == "29% of float · 6.9 days to cover (Yahoo ratio)"
    assert "Yahoo's short ratio" in check["source"]
    undated = by_id(read(facts(float_shares=300_081, short_interest=88_477), NOW))["short_interest"]
    assert undated["as_of"] is None and undated["detail"] == "88K shares short"


def test_a_contradicted_float_is_marked_and_says_why_without_changing_the_read():
    """#532: WHLR's 54K float against 568K shares out reads "54K?" with the reason; the check and the likely
    cause are the same as for an uncontradicted float (point 2, the gates, waits on the operator)."""
    reason = "Float 54K is under half of the 568K shares not held by insiders"
    base = dict(change_pct=0.9, volume=5_000_000, float_shares=54_000, rel_volume=40.0, catalyst=NONE)
    flagged = read(facts(**base, float_contradicted=True, float_contradicted_reason=reason), NOW)
    plain = read(facts(**base), NOW)
    check = by_id(flagged)["float"]
    assert check["value"] == "54K? shares -- low float"
    assert check["detail"] == reason
    assert check["state"] == by_id(plain)["float"]["state"] == "yes"
    assert flagged["likely"] == plain["likely"]
    assert by_id(read(facts(**base, float_contradicted=False), NOW))["float"]["value"] == "54K shares -- low float"
