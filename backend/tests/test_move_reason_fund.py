"""A fund names what it tracks (ADR 028 amendment 4): BRZD and BZQ read "Unexplained" on 2026-10-26, the morning
after Lula won Brazil's runoff -- inverse Brazil funds, with no company news to find."""
from __future__ import annotations

import pytest

from move_reason.fund import cause_label, describe, from_name, is_fund
from move_reason.rules import read
from tests.test_move_reason_rules import NOISE, NONE, NOW, facts


@pytest.mark.parametrize("name, side, leverage, tracks", [
    # Yahoo's spelling and Massive's of the same ETN.
    ("MicroSectors -3\u00d7 Short Brazil Etns", "inverse", 3.0, "Brazil"),
    ("MicroSectors -3x Short Brazil ETNs", "inverse", 3.0, "Brazil"),
    ("ProShares UltraShort MSCI Brazil Capped", "inverse", 2.0, "Brazil"),
    ("ProShares UltraPro Short QQQ", "inverse", 3.0, "QQQ"),
    ("ProShares Short QQQ", "inverse", 1.0, "QQQ"),
    ("T-REX 2X Inverse CRWV Daily Target ETF", "inverse", 2.0, "CRWV"),
    ("Defiance Daily Target 2X Short AMD ETF", "inverse", 2.0, "AMD"),
    ("Direxion Daily Semiconductor Bear 3X Shares", "inverse", 3.0, "Semiconductor"),
    ("GraniteShares 2x Long NBIS Daily ETF", "long", 2.0, "NBIS"),
    ("ProShares Ultra MSCI Brazil Capped", "long", 2.0, "Brazil"),
    ("iShares MSCI Brazil ETF", "long", 1.0, "Brazil"),
    # "Short" as a bond's duration is never a side.
    ("iShares Short Treasury Bond ETF", "long", 1.0, "Treasury Bond"),
    # Short through options (held-back set 3: WNTR and FIAT read long, 6 wrong directions).
    ("YieldMax MSTR Short Option Income Strategy ETF", "inverse", 1.0, "MSTR"),
    ("YieldMax Short COIN Option Income Strategy ETF", "inverse", 1.0, "COIN"),
])
def test_a_fund_name_says_its_side_leverage_and_what_it_tracks(name, side, leverage, tracks):
    f = from_name(name)
    assert (f["side"], f["leverage"], f["tracks"]) == (side, leverage, tracks)


def test_the_legal_tail_and_an_unwritten_multiple_are_read_honestly():
    # The first held-back review (2026-10-26) found these three: a legal tail hid what the fund tracks, and
    # "Leveraged" with no number read as 1x.
    assert from_name("21Shares Sui Staking ETF Common Shares of Beneficial Interest Shares")["tracks"] == "Sui"
    oil = from_name("MicroSectors U.S. Big Oil 3x Leveraged ETNs due February 17, 2045")
    assert (oil["leverage"], oil["tracks"]) == (3.0, "Big Oil")
    mst = from_name("Defiance Leveraged Long Income MSTR ETF")
    assert mst["leverage"] is None and describe(mst) == "Leveraged fund on MSTR"


def test_a_ticker_that_is_also_a_word_and_a_sponsor_name_are_read_right():
    # The second held-back review (2026-10-26): "ON" and "BULL" were dropped as words; a sponsor's
    # "Capital Group, LLC" was read as what the fund tracks.
    assert from_name("Leverage Shares 2X Long ON Daily ETF")["tracks"] == "ON"
    assert from_name("Leverage Shares 2X Long BULL Daily ETF")["tracks"] == "BULL"
    assert from_name("Canary Capital Group, LLC Canary Litecoin ETF")["tracks"] == "Litecoin"


def test_a_name_that_does_not_say_what_it_tracks_keeps_the_rest():
    f = from_name("ETRACS Quarterly Pay 1.5x Leveraged MarketVector BDC Liquid Index ETN Series B Due 2050")
    assert f["leverage"] == 1.5 and describe(f).startswith("Leveraged 1.5x fund")


def test_yahoo_quote_type_decides_a_fund_and_unknown_stays_unknown():
    assert is_fund("ETF") is True and is_fund("EQUITY") is False and is_fund(None) is None


def test_the_cause_says_a_direction_never_a_percentage_for_the_tracked_market():
    bzq = from_name("ProShares UltraShort MSCI Brazil Capped")
    assert cause_label(bzq, 0.503) == "Inverse 2x fund on Brazil: up 50.3%, so Brazil fell"
    assert cause_label(bzq, -0.2) == "Inverse 2x fund on Brazil: down 20.0%, so Brazil rose"
    nbil = from_name("GraniteShares 2x Long NBIS Daily ETF")
    assert cause_label(nbil, 0.53) == "Leveraged 2x fund on NBIS: up 53.0%, so NBIS rose"


def test_bzq_on_2026_10_26_reads_a_fund_not_unexplained():
    out = read(facts(change_pct=0.503, catalyst=NOISE, quote_type="ETF",
                     fund=from_name("ProShares UltraShort MSCI Brazil Capped")), NOW)
    assert out["likely"]["kind"] == "fund"
    assert out["likely"]["label"] == "Inverse 2x fund on Brazil: up 50.3%, so Brazil fell"
    assert out["likely"]["detail"] == "Read from its name: ProShares UltraShort MSCI Brazil Capped"
    check = {c["id"]: c for c in out["checks"]}["fund"]
    assert check["state"] == "yes" and check["value"] == "Inverse 2x fund on Brazil"


def test_a_fund_with_company_news_keeps_the_news():
    news = {"verdict": "catalyst", "category": "merger_acquisition", "source": "globenewswire",
            "title": "Sponsor to liquidate the fund", "sources_answered": ["alpaca"]}
    out = read(facts(change_pct=0.3, catalyst=news, quote_type="ETF", fund=from_name("iShares MSCI Brazil ETF")), NOW)
    assert out["likely"]["kind"] == "news"


def test_a_company_and_an_unread_security_type_never_read_as_a_fund():
    stock = read(facts(change_pct=0.4, catalyst=NONE, quote_type="EQUITY", fund=None), NOW)
    assert stock["likely"]["kind"] != "fund"
    assert {c["id"]: c for c in stock["checks"]}["fund"]["value"] == "Not a fund (Yahoo: equity)"
    unread = read(facts(change_pct=0.4, catalyst=NONE), NOW)
    assert {c["id"]: c for c in unread["checks"]}["fund"]["state"] == "unknown"
    assert unread["likely"]["kind"] != "fund"
