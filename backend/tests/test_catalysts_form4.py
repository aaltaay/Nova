"""Form 4 open-market purchases by officers and directors as a weak catalyst (#517, ADR 024).

The fixtures under ``fixtures/form4/`` are built by hand from SEC's documented ownership schema
(X0508) -- SEC's site was unreachable where they were written. BFRG's issuer CIK (1829247) and the
filing time (2026-09-22 16:45 ET) are from #517; the owners' names and the amounts are illustrative.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from catalysts import form4
from catalysts.classify import classify_item, verdict
from constants_catalysts import CATALYST_INSIDER_BUY_MIN_USD, CATALYST_RULES_VERSION

FIXTURES = Path(__file__).parent / "fixtures" / "form4"


def load(name: str) -> form4.Filing:
    filing = form4.parse(FIXTURES.joinpath(name).read_bytes())
    assert filing is not None
    return filing


def test_a_ceo_purchase_read_from_the_full_submission():
    filing = load("bfrg_ceo_purchase.txt")
    assert (filing.document_type, filing.issuer_cik, filing.issuer_symbol) == ("4", "1829247", "BFRG")
    buy = form4.insider_purchase(filing)
    assert buy is not None and buy.shares == 35_000 and buy.unpriced == 0
    assert buy.total_usd == pytest.approx(20_000 * 1.62 + 15_000 * 1.655)
    assert buy.owners[0].role == "CEO, Director"
    assert form4.title(buy) == "Form 4: open-market purchase by Example Chief (CEO, Director), 35,000 shares ($57k)"
    assert form4.stamp(buy.total_usd) == "P:57225"
    assert "20,000 sh at $1.62 on 2026-09-22 = $32,400" in form4.summary(buy)
    assert "15,000 sh at $1.655" in form4.summary(buy)


def test_only_the_purchase_counts_among_exercises_sales_grants_gifts_and_withholding():
    filing = load("officer_buys_and_sells.xml")
    assert [t.code for t in filing.trades] == ["M", "S", "A", "F", "G", "P"]   # the derivative table is not read
    buy = form4.insider_purchase(filing)
    assert buy is not None and [t.code for t in buy.trades] == ["P"]
    assert (buy.shares, buy.total_usd) == (5_000, 30_000.0)
    assert buy.owners[0].role == "EVP, CFO"                                      # "true" / "false" flags read


def test_a_filing_with_sales_and_no_purchase_is_not_one():
    filing = load("officer_buys_and_sells.xml")
    sells_only = form4.Filing(filing.document_type, filing.issuer_cik, filing.issuer_symbol, filing.owners,
                              tuple(t for t in filing.trades if t.code != "P"))
    assert form4.insider_purchase(sells_only) is None


def test_a_directors_purchase_counts():
    filing = load("director_purchase.xml")
    assert filing.issuer_symbol == "ACME"
    buy = form4.insider_purchase(filing)
    assert buy is not None and buy.owners[0].role == "Director" and buy.total_usd == pytest.approx(2_100)


def test_a_ten_percent_owner_alone_is_not_management():
    filing = load("ten_percent_owner_purchase.xml")
    assert filing.owners[0].ten_percent and not filing.owners[0].insider
    assert form4.insider_purchase(filing) is None
    # ... unless the joint filing also names an officer or a director.
    raw = FIXTURES.joinpath("ten_percent_owner_purchase.xml").read_text()
    director = ("<reportingOwner><reportingOwnerId><rptOwnerCik>0009990005</rptOwnerCik><rptOwnerName>Example Partner"
                "</rptOwnerName></reportingOwnerId><reportingOwnerRelationship><isDirector>1</isDirector>"
                "</reportingOwnerRelationship></reportingOwner>")
    joint = form4.parse(raw.replace("<nonDerivativeTable>", director + "<nonDerivativeTable>"))
    buy = form4.insider_purchase(joint)
    assert buy is not None and [o.name for o in buy.owners] == ["Example Partner"] and buy.total_usd == 2_000_000


def test_an_unpriced_purchase_counts_its_shares_not_a_value():
    filing = load("director_purchase.xml")
    unpriced = form4.Filing(filing.document_type, filing.issuer_cik, filing.issuer_symbol, filing.owners,
                            (form4.Trade("P", 1_000.0, None, True, "2026-09-22"),))
    buy = form4.insider_purchase(unpriced)
    assert buy is not None and (buy.total_usd, buy.unpriced) == (0.0, 1)
    assert form4.title(buy).endswith("(price not stated)")


@pytest.mark.parametrize("raw", ["", "<html>Not Found</html>", "<ownershipDocument><issuer></ownershipDocument>"])
def test_an_unreadable_document_is_none(raw):
    assert form4.parse(raw) is None


def test_the_stamp_round_trips_and_nothing_else_reads_as_one():
    assert form4.stamped_usd(form4.stamp(57_225.4)) == 57_225.0
    assert form4.stamped_usd("2.02,9.01") is None and form4.stamped_usd(None) is None and form4.stamped_usd("P:") is None
    assert [form4.money(v) for v in (950, 57_225, 1_234_567)] == ["$950", "$57k", "$1.2M"]


# -- classification (rules v7) -------------------------------------------------------------------
def form4_label(usd):
    lb = classify_item("Form 4: open-market purchase by Example Chief (CEO), 1 shares ($1)", "", source="edgar",
                       form="4", sec_items=None if usd is None else form4.stamp(usd))
    return (lb.kind, lb.category, lb.strength)


def test_a_purchase_at_or_over_the_threshold_is_a_weak_catalyst():
    assert CATALYST_RULES_VERSION.startswith("catalyst-rules-v7")
    assert form4_label(57_225) == ("catalyst", "listing_financing", "weak")
    assert form4_label(CATALYST_INSIDER_BUY_MIN_USD) == ("catalyst", "listing_financing", "weak")


@pytest.mark.parametrize("usd", [2_100, CATALYST_INSIDER_BUY_MIN_USD - 1, 0, None])
def test_a_token_or_unstamped_purchase_is_routine(usd):
    assert form4_label(usd) == ("routine", "corporate_routine", None)


def test_bfrg_the_filing_names_the_catalyst_benzinga_only_hinted_at():
    """BFRG 2026-09-23: +24% premarket; the only article was a movers piece, the cause two Form 4s filed
    at 16:45 ET the evening before (#517). The verdict was ``noise_only``; the filing now places it."""
    filed = 1_789_000_000.0                      # 2026-09-22 16:45 ET-ish; only the order matters here
    buy = form4.insider_purchase(load("bfrg_ceo_purchase.txt"))
    items = [
        {"title": "BullFrog AI Holdings Stock Climbs Over 24% Pre-Market: Here's What You Need to Know",
         "source": "alpaca", "publisher": "Benzinga", "n_tickers": 1, "published_ts": filed + 40_000,
         "url": "https://www.benzinga.com/trading-ideas/movers/26/09/1/"
                "bullfrog-ai-bfrg-stock-jumps-premarket-ceo-cfo-insider-buying"},
        {"title": form4.title(buy), "summary": form4.summary(buy), "source": "edgar", "publisher": "SEC EDGAR",
         "n_tickers": 1, "form": "4", "sec_items": form4.stamp(buy.total_usd), "published_ts": filed},
    ]
    before = verdict(items[:1], window_start=filed - 3_000, cutoff=filed + 50_000, sources_answered=["alpaca"])
    assert before["verdict"] == "noise_only"
    v = verdict(items, window_start=filed - 3_000, cutoff=filed + 50_000, sources_answered=["alpaca", "edgar"])
    assert (v["verdict"], v["category"], v["strength"], v["source"]) == ("catalyst", "listing_financing", "weak", "edgar")
    assert v["title"].startswith("Form 4: open-market purchase by Example Chief")
