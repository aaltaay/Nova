"""A fund says so, in its own name (ADR 028 amendment 4): BRZD and BZQ read "Unexplained" on 2026-10-26, the
morning after Lula won Brazil's runoff -- inverse Brazil funds, with no company news to find. The read quotes the
fund's name and reads nothing out of it (reading it failed its held-back bar four times)."""
from __future__ import annotations

from move_reason.fund import CAUSE_LABEL, fact, is_fund, named
from move_reason.rules import read
from tests.test_move_reason_rules import NOISE, NONE, NOW, facts

BZQ = "ProShares UltraShort MSCI Brazil Capped"


def by_id(out):
    return {c["id"]: c for c in out["checks"]}


def test_yahoo_quote_type_decides_a_fund_and_unknown_stays_unknown():
    assert is_fund("ETF") is True and is_fund("etf") is True and is_fund("MUTUALFUND") is True
    assert is_fund("EQUITY") is False and is_fund(None) is None and is_fund("") is None


def test_the_name_is_quoted_as_yahoo_gives_it():
    # Yahoo's own spelling, "x" as the multiplication sign and all, untouched.
    assert fact("MicroSectors -3× Short Brazil Etns") == {"name": "MicroSectors -3× Short Brazil Etns"}
    assert fact("  ") == {"name": None} and fact(None) == {"name": None}
    assert named({"name": None}, "ETF") == "A fund (Yahoo: etf)"


def test_bzq_on_2026_10_26_reads_a_fund_not_unexplained():
    out = read(facts(change_pct=0.503, catalyst=NOISE, quote_type="ETF", fund=fact(BZQ)), NOW)
    assert out["likely"]["kind"] == "fund"
    assert out["likely"]["label"] == CAUSE_LABEL == "A fund: it moves with what it tracks, not on company news"
    assert out["likely"]["detail"] == BZQ
    assert out["likely"]["confidence"] == "likely"
    check = by_id(out)["fund"]
    assert (check["state"], check["value"], check["detail"]) == ("yes", BZQ, "Yahoo: etf")
    rung = {s["kind"]: s for s in out["likely"]["steps"]}["fund"]
    assert rung == {"kind": "fund", "name": "A fund", "fits": True, "why": f"{BZQ} (Yahoo: etf)"}


def test_a_falling_fund_reads_the_same_way():
    out = read(facts(change_pct=-0.4, catalyst=NONE, quote_type="ETF", fund=fact("iShares MSCI Brazil ETF")), NOW)
    assert out["likely"]["kind"] == "fund" and out["likely"]["detail"] == "iShares MSCI Brazil ETF"


def test_a_fund_with_company_news_keeps_the_news():
    news = {"verdict": "catalyst", "category": "merger_acquisition", "source": "globenewswire",
            "title": "Sponsor to liquidate the fund", "sources_answered": ["alpaca"]}
    out = read(facts(change_pct=0.3, catalyst=news, quote_type="ETF", fund=fact("iShares MSCI Brazil ETF")), NOW)
    assert out["likely"]["kind"] == "news"


def test_a_company_and_an_unread_security_type_never_read_as_a_fund():
    stock = read(facts(change_pct=0.4, catalyst=NONE, quote_type="EQUITY", fund=None), NOW)
    assert stock["likely"]["kind"] != "fund"
    assert by_id(stock)["fund"]["value"] == "Not a fund (Yahoo: equity)"
    unread = read(facts(change_pct=0.4, catalyst=NONE), NOW)
    assert by_id(unread)["fund"]["state"] == "unknown" and unread["likely"]["kind"] != "fund"
