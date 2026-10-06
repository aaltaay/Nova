"""Splits a rebuild confirms from SEC filings (#772): reading a ratio and an effective date out of
a filing, holding them against the overnight prices, finding the suspects, and the days a split
touches. Pure: no network, no flat files."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "leaderboard"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import split_confirm as sc  # noqa: E402

# PHGE's 8-K of 2026-09-09 (Item 5.03), as SEC holds it.
PHGE = (
    "Item 5.03 Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year. Reverse Stock Split. "
    "On September 3, 2026, BiomX Inc. (the “Company”) filed a Certificate of Amendment to its Amended and "
    "Restated Certificate of Incorporation (the “Split Amendment”) with the Secretary of State of the State of "
    "Delaware, which became effective at 12:01 a.m., Eastern Time, on September 9, 2026. The Split Amendment effected "
    "a one-for-ten reverse stock split of the Company’s common stock, par value $0.0001 per share (the “Common "
    "Stock”), and reduced the number of authorized shares of Common Stock from 750,000,000 to 150,000,000. Trading "
    "in the Common Stock on a split-adjusted basis on the NYSE American commences with the market open on September 9, "
    "2026 under the new CUSIP number 09090D 608. Name Change. On September 3, 2026, the Company filed a Certificate of "
    "Amendment ... which will become effective at 12:01 a.m., Eastern Time, on September 11, 2026."
)
SEP8, SEP9, SEP10 = date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)
AUG3, AUG4 = date(2026, 8, 3), date(2026, 8, 4)


def ratios(text: str) -> list[tuple[int, int]]:
    return sorted((m.split_from, m.split_to) for m in sc.mentions(text))


def test_phge_reads_one_for_ten_effective_on_the_session():
    assert ratios(PHGE) == [(10, 1)]
    assert SEP9 in sc.effective_dates(PHGE)
    v = sc.judge(PHGE, prev_session=SEP8, session=SEP9, prev_close=0.155, open_=1.60)
    assert v.confirmed and (v.split_from, v.split_to) == (10, 1)
    assert v.date_match is True and v.adjusted_ratio == pytest.approx(1.6 / 1.55, abs=1e-4)
    assert "one-for-ten reverse stock split" in v.ratio_text


def test_the_split_is_refused_on_another_session():
    v = sc.judge(PHGE, prev_session=SEP9, session=SEP10, prev_close=1.62, open_=1.66)
    assert not v.confirmed and "not after 2026-09-09 and by 2026-09-10" in v.reason


@pytest.mark.parametrize(("text", "expected"), [
    ("The Company effected a 1-for-25 reverse stock split, effective on August 4, 2026.", [(25, 1)]),
    ("Upon the reverse stock split, one (1) share will be issued for every twenty-five (25) shares outstanding.", [(25, 1)]),
    ("The reverse stock split became effective. Every twenty-five (25) shares of common stock issued and outstanding "
     "were automatically combined into one (1) share.", [(25, 1)]),
    ("The share consolidation on a 1:25 basis became effective on August 4, 2026.", [(25, 1)]),
    ("The Board approved a two-for-one forward stock split.", [(1, 2)]),
    ("The Company effected a one-for-one hundred fifty reverse stock split.", [(150, 1)]),
])
def test_ratios_in_the_ways_filings_write_them(text, expected):
    assert ratios(text) == expected


def test_a_range_or_a_clock_time_is_no_ratio():
    assert ratios("Stockholders approved a reverse stock split at a ratio in the range of 1-for-5 to 1-for-50.") == []
    assert ratios("The board may effect a reverse stock split of up to 1-for-20 at its discretion.") == []
    assert ratios("The amendment became effective at 12:01 a.m. on August 4, 2026, effecting the reverse stock split.") == []
    assert ratios("The Company entered into a one-for-one exchange of warrants.") == []   # no split named


def test_a_ratio_dated_elsewhere_is_another_split():
    text = ("The Company previously effected a 1-for-19 reverse stock split on November 25, 2025. On August 4, 2026 "
            "the Company effected a 1-for-25 reverse stock split, and its shares began trading on a split-adjusted basis "
            "on August 4, 2026.")
    v = sc.judge(text, prev_session=AUG3, session=AUG4, prev_close=0.20, open_=4.9)
    assert v.confirmed and (v.split_from, v.split_to) == (25, 1)
    only_old = "The Company effected a 1-for-19 reverse stock split on November 25, 2025, effective that day."
    refused = sc.judge(only_old, prev_session=AUG3, session=AUG4, prev_close=0.20, open_=3.8)
    assert not refused.confirmed


def test_the_price_must_agree_and_a_missing_date_tightens_the_band():
    text = "The Company effected a 1-for-10 reverse stock split of its common stock."
    assert sc.judge(text, prev_session=AUG3, session=AUG4, prev_close=0.20, open_=2.0).confirmed
    loose = sc.judge(text, prev_session=AUG3, session=AUG4, prev_close=0.20, open_=3.6)   # 1.8x: fine with a date
    assert not loose.confirmed and loose.reason.startswith("the price disagrees")
    assert sc.judge(text, prev_session=AUG3, session=AUG4, prev_close=0.20, open_=2.0).date_match is None
    wrong_way = sc.judge(text, prev_session=AUG3, session=AUG4, prev_close=0.20, open_=0.12)
    assert not wrong_way.confirmed


def test_a_filing_naming_no_split_is_said_so():
    v = sc.judge("Item 5.03 The Company amended its bylaws to change the quorum.", prev_session=AUG3, session=AUG4,
                 prev_close=1.0, open_=3.0)
    assert not v.confirmed and not v.names_split and v.reason == "names no split"


def test_suspects_are_the_jumps_no_listed_split_explains():
    prev = {"JUMP": (1.0, 0.155, 6_500_000), "LISTED": (1.0, 0.10, 1000), "CALM": (5.0, 5.0, 10), "DROP": (9.0, 9.0, 100)}
    cur = {"JUMP": (1.60, 1.62, 745_000), "LISTED": (2.0, 2.0, 50), "CALM": (5.5, 5.6, 10), "DROP": (4.0, 4.1, 500)}
    found = sc.suspects(prev, cur, prev_session=SEP8, session=SEP9, universe=["JUMP", "LISTED", "CALM", "DROP"],
                        listed={"LISTED": [SEP9]}, up=1.8, down=0.7)
    assert [(s.ticker, s.price_ratio) for s in found] == [("DROP", pytest.approx(4 / 9, abs=1e-4)),
                                                          ("JUMP", pytest.approx(10.3226, abs=1e-4))]
    assert found[1].volume_ratio == pytest.approx(745_000 / 6_500_000, abs=1e-4)


def test_a_split_touches_its_day_and_the_next_sessions_that_traded():
    cal = [date(2026, 9, d) for d in (4, 8, 9, 10, 11, 14, 15)]
    assert sc.affected_sessions(SEP9, cal, {SEP10, date(2026, 9, 15)}, lookback=3) == [SEP9, SEP10]
    assert sc.affected_sessions(date(2026, 9, 12), cal, set(), lookback=3) == []
