"""Rules v8 (ADR 024 amendment 2026-10-02): AMOD's missed catalyst, from the exact items of that day.

AMOD ran +120% on 2026-10-02 while the desk read "noise_only". Its 8-K (accepted 2026-10-01 11:30:52 ET)
closed a PIPE of 51.6M shares for 3,170 bitcoin; Benzinga's after-hours piece named that cause in its summary
but was tagged AMOD + BTCUSD, so it was never read as a one-ticker rewrite.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from catalysts import feed as feed_mod
from catalysts import live
from catalysts.classify import best_placed, classify_item, label_of, shares_issued, ticker_count, verdict
from catalysts.windows import memory_cutoff, prior_session_open, window_start

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 2, 8, 40, tzinfo=ET).timestamp()          # Friday, AMOD +120% premarket
PRIOR_CLOSE = datetime(2026, 10, 1, 16, 0, tzinfo=ET).timestamp()
PRIOR_OPEN = datetime(2026, 10, 1, 4, 0, tzinfo=ET).timestamp()

# edgar:0001493152-26-045296, as the live catalyst feed stored it (the 8-K's Item text; no release headline).
AMOD_8K = {
    "item_id": "edgar:0001493152-26-045296", "source": "edgar", "published_ts": 1790868652.0,
    "title": "8-K: Acquisition completed; Other events", "publisher": "SEC EDGAR", "n_tickers": 2,
    "form": "8-K", "sec_items": "2.01,8.01",
    "url": "https://www.sec.gov/Archives/edgar/data/1862463/000149315226045296/0001493152-26-045296-index.htm",
    "summary": (
        "Item 2.01. Completion of Acquisition or Disposition of Assets. As disclosed in the Current Report on Form "
        "8-K filed on August 27, 2026, by Alpha Modus Holdings, Inc. (the “ Company ”), on August 26, 2026, "
        "the Company entered into a securities purchase agreement (the “ SPA ”) with the non-U.S. investors "
        "named therein (the “ Investors ”), pursuant to which the Company agreed to issue and sell to the "
        "Investors, and the Investors agreed to purchase from the Company, an aggregate of (i) 51,621,560 shares of "
        "Class A Common Stock (the “ Shares ”), and (ii) warrants to purchase an additional 51,621,560 shares "
        "for a $4.36/share exercise price (the “ Warrants ”), for an aggregate purchase price consisting of "
        "3,170 bitcoin (such transaction the “ PIPE Transaction ”). On September 30, 2026, the Company closed "
        "the PIPE Transaction, issuing the Shares and the Warrants to the Investors, and the Investors delivered 3,170 "
        "bitcoin to the custody and control of a newly-formed, wholly-owned subsidiary of the Company, AMOD Tech Pte. "
        "Ltd., a Singapore private company limited by shares. As a result of closing the PIPE Transaction, the "
        "Company’s subsidiary now owns 3,170 bitcoin having a value in excess of $250 million based on a reference "
        "price of approximately $83,612.20 per bitcoin on September 30, 2026. Item 8.01. Other Events. As disclosed "
        "in the Current Report on Form 8-K filed on April 10, 2026, by the "),
}
# edgar:0001493152-26-045442 (08:35 ET on 2026-10-02): Nasdaq's letter that the company complies again.
AMOD_8K_COMPLIANCE = {
    "item_id": "edgar:0001493152-26-045442", "source": "edgar", "published_ts": 1790944536.0,
    "title": "8-K: Other events", "publisher": "SEC EDGAR", "n_tickers": 2, "form": "8-K", "sec_items": "8.01",
    "url": "https://www.sec.gov/Archives/edgar/data/1862463/000149315226045442/0001493152-26-045442-index.htm",
    "summary": (
        "Item 8.01. Other Events. On October 1, 2026, Alpha Modus Holdings, Inc. (the “ Company ”) received a "
        "letter from the Listing Qualifications Department of the Nasdaq Stock Market (“ Nasdaq ”) indicating "
        "that based on the Company’s Current Report on Form 8-K filed on October 1, 2026, Nasdaq’s staff had "
        "determined that the Company complies with Listing Rule 5550(b)(1). The staff noted that if the Company fails "
        "to evidence compliance in its next periodic report, it may be subject to delisting."),
}
# Alpaca / Benzinga news, as Alpaca's /v1beta1/news answered for AMOD.
REWRITE = {  # alpaca:62126197, 2026-10-02 00:34:28 ET
    "id": 62126197, "created_at": "2026-10-02T04:34:28Z", "source": "benzinga", "symbols": ["AMOD", "BTCUSD"],
    "headline": "Bitcoin Boost Gives Alpha Modus (AMOD) Stock 61% Spike After Hours: What You Should Know",
    "summary": ("Alpha Modus Holdings shares surged 60.68% after hours after closing a bitcoin-funded private "
                "placement and regaining Nasdaq compliance."),
    "url": ("https://www.benzinga.com/markets/equities/26/10/62126197/"
            "alpha-modus-holdings-shares-after-hours-bitcoin-private-placement"),
}
NEWSDESK = {  # alpaca:62112633, 2026-10-01 11:39:50 ET (the prior session)
    "id": 62112633, "created_at": "2026-10-01T15:39:50Z", "source": "benzinga", "symbols": ["AMOD"], "summary": "",
    "headline": ("Alpha Modus Closes PIPE Deal, Receives 3,170 Bitcoin On Sept. 30; Subsidiary Owns 3,170 Bitcoin "
                 "Valued At Over $250M As Of Sept. 30"),
    "url": "https://www.benzinga.com/news/26/10/62112633/alpha-modus-closes-pipe-deal-receives-3-170-bitcoin-sept-30",
}
MOVERS = {  # alpaca:62130425, 2026-10-02 08:05:56 ET
    "id": 62130425, "created_at": "2026-10-02T12:05:56Z", "source": "benzinga",
    "symbols": ["AIXI", "AMOD", "BKYI", "ICG", "MBAI", "RPGL", "RVSN", "SGRX", "SMX", "STX", "SYNA", "WCT"],
    "headline": "12 Information Technology Stocks Moving In Friday's Pre-Market Session", "summary": "Gainers",
    "url": ("https://www.benzinga.com/trading-ideas/movers/26/10/62130425/"
            "12-information-technology-stocks-moving-friday-s-pre-market-session"),
}


def lb(item):
    out = label_of(item)
    return (out.kind, out.category, out.strength, out.dilution)


def alpaca_label(n, n_tickers=None):
    return lb({"title": n["headline"], "summary": n["summary"], "source": "alpaca", "publisher": n["source"],
               "n_tickers": ticker_count(n["symbols"]) if n_tickers is None else n_tickers, "url": n["url"]})


TREASURY = ("catalyst", "crypto_treasury", "weak", True)


# -- the label --------------------------------------------------------------------------------------------
def test_the_8k_that_closed_the_bitcoin_pipe_is_a_crypto_treasury_raise():
    # v7 read it as plain offering_dilution: "bitcoin" sits past the 600 characters the classes read.
    assert lb(AMOD_8K) == TREASURY


def test_the_after_hours_rewrite_is_read_by_the_cause_it_names():
    assert ticker_count(REWRITE["symbols"]) == 1           # AMOD + the coin the story is about
    assert alpaca_label(REWRITE) == TREASURY
    # Counted as two symbols (v7), it was not a one-ticker piece and stayed a movers list.
    assert alpaca_label(REWRITE, n_tickers=2)[:2] == ("noise", "movers_list")


def test_the_newsdesk_headline_reads_a_pipe_paid_in_bitcoin():
    assert alpaca_label(NEWSDESK) == TREASURY


def test_the_compliance_letter_stays_a_routine_filing():
    # Kept routine on purpose: as a catalyst it would outrank the treasury rewrite as the verdict's item.
    assert lb(AMOD_8K_COMPLIANCE)[:2] == ("routine", "filing_other")


@pytest.mark.parametrize("title, expected", [
    ("BitMine Announces $250M Private Placement Of 55.56M Shares Of Common Stock At $4.50/Share To Launch "
     "Ethereum Treasury Strategy", TREASURY),
    ("Profusa Announces $100 Million Equity Line of Credit to Initiate Bitcoin Treasury Strategy", TREASURY),
    ("Bitcoin Miner Acme Prices $20 Million Registered Direct Offering", ("negative", "offering_dilution", None, False)),
    ("Acme Raises $30M In Private Placement To Purchase Bitcoin Mining Rigs",
     ("negative", "offering_dilution", None, False)),
    ("Velo3D Announces $30M PIPE Financing Issuing ~3.6M Shares At $8.25/Share",
     ("negative", "offering_dilution", None, False)),
    ("Eightco Announces Multi-Month Lock-Up Extension Of Its PIPE Investors", ("catalyst", "company_news", "weak", False)),
    ("Acme Announces Pipeline Update", ("catalyst", "company_news", "weak", False)),
])
def test_treasury_raises_and_pipes(title, expected):
    assert lb({"title": title, "source": "alpaca", "n_tickers": 1}) == expected


def test_a_cause_named_after_the_words_after_hours_is_kept():
    # "after hours" anchors the clause that names the cause with "on": v8 keeps it (skipping it lost 20 of these).
    out = classify_item("Concrete Pumping Holdings Stock Surges 23% Pre-Market: Why Is It Moving?",
                        "Concrete Pumping Holdings shares jumped roughly 23% after-hours on earnings beat and raised "
                        "FY2026 guidance.", source="alpaca", n_tickers=1)
    assert (out.kind, out.category) == ("catalyst", "earnings_guidance")


@pytest.mark.parametrize("symbols, n", [
    (["AMOD", "BTCUSD"], 1),
    (["IONQ", "IONQ.WS"], 1),
    (["RUM", "USDTUSD"], 1),
    (["BB", "BTCUSD", "NVDA", "ZECUSD"], 4),   # several pairs: a crypto market piece, still a roundup
    (["BTCUSD"], 1),
    (["BTC/USD", "ETH/USD"], 2),
    (["AAPL", "MSFT"], 2),
    ([], 0),
])
def test_ticker_count(symbols, n):
    assert ticker_count(symbols) == n


# -- the window and the prior session ---------------------------------------------------------------------
def test_the_window_still_opens_at_the_prior_close():
    v = verdict([AMOD_8K], window_start=window_start(NOW), cutoff=NOW, sources_answered=["edgar"])
    assert v["verdict"] == "none_found"                     # a day-old release is never today's catalyst
    prior = best_placed([AMOD_8K, AMOD_8K_COMPLIANCE], start=prior_session_open(NOW), end=window_start(NOW))
    assert prior is not None and prior["category"] == "crypto_treasury" and prior["dilution"] is True
    assert prior["source"] == "edgar" and prior["published_ts"] == AMOD_8K["published_ts"]
    assert best_placed([AMOD_8K_COMPLIANCE], start=prior_session_open(NOW), end=NOW) is None  # routine: none


def test_windows_on_the_exchange_calendar():
    assert window_start(NOW) == PRIOR_CLOSE
    assert prior_session_open(NOW) == PRIOR_OPEN
    monday = datetime(2026, 10, 5, 9, 0, tzinfo=ET).timestamp()
    friday_open = datetime(2026, 10, 2, 4, 0, tzinfo=ET).timestamp()
    assert prior_session_open(monday) == friday_open
    assert memory_cutoff(monday) == friday_open             # 40 hours would stop on Saturday
    assert memory_cutoff(NOW) == NOW - 40 * 3600            # the longer of the two


def test_the_feed_keeps_fridays_filings_over_the_weekend():
    monday = datetime(2026, 10, 5, 9, 0, tzinfo=ET).timestamp()
    f = feed_mod.CatalystFeed(fetch=lambda url, headers: b"", clock=lambda: monday)
    friday_8k = {**AMOD_8K, "published_ts": datetime(2026, 10, 2, 11, 30, tzinfo=ET).timestamp(),
                 "tickers": ["AMOD"]}
    f._remember(friday_8k)
    f._prune(monday)
    assert [it["item_id"] for it in f.items_for("AMOD", 0, monday)] == [AMOD_8K["item_id"]]


@pytest.fixture
def _desk(monkeypatch):
    live.reset_for_testing()
    feed = [AMOD_8K, AMOD_8K_COMPLIANCE]
    monkeypatch.setattr(live, "_feed_view", lambda sym, start, now, coverage=True: (
        [it for it in feed if sym == "AMOD" and start < it["published_ts"] <= now], ["edgar"] if coverage else []))
    yield
    live.reset_for_testing()


def test_the_live_verdict_names_the_prior_session_and_counts_the_rewrite(_desk):
    live.record(["AMOD"], [REWRITE, MOVERS], start=PRIOR_CLOSE, through=NOW)
    v = live.verdict_for("AMOD", NOW)
    assert (v["verdict"], v["category"], v["source"]) == ("catalyst", "crypto_treasury", "alpaca")
    assert v["negative_too"] is True                        # the raise is dilution too
    assert v["prior_session"]["category"] == "crypto_treasury"
    assert v["prior_session"]["source"] == "edgar"
    assert live.compact(v)["prior_session"] == v["prior_session"]


def test_with_only_movers_lists_today_the_prior_session_is_named_not_counted(_desk, monkeypatch):
    early = datetime(2026, 10, 2, 8, 20, tzinfo=ET).timestamp()   # before the 08:35 compliance filing
    monkeypatch.setattr(live, "ensure", lambda symbols, now=None: None)
    monkeypatch.setattr(live.live_finnhub, "ensure", lambda symbol, start, now=None: None)
    live.record(["AMOD"], [MOVERS], start=PRIOR_CLOSE, through=early)
    v = live.verdict_for("AMOD", early)
    assert v["verdict"] == "noise_only" and v["negative_too"] is False
    assert v["prior_session"]["published_ts"] == AMOD_8K["published_ts"]
    assert live.panel("AMOD", early)["verdict"]["prior_session"]["title"] == AMOD_8K["title"]


def test_the_issuance_map_reads_the_8k_from_the_store_for_30_days(tmp_path):
    from catalysts import feed_store, issuance

    db = feed_store.connect(tmp_path / "catalyst_feed.sqlite3")
    feed_store.put_items(db, [{**AMOD_8K, "tickers": ["AMOD", "AMODW"]},
                              {**AMOD_8K_COMPLIANCE, "tickers": ["AMOD", "AMODW"]}])
    issuance.reset_for_testing()
    try:
        assert issuance.refresh(NOW, db) == 2                   # AMOD and its warrant
        hit = issuance.for_symbol("amod")
        assert hit["published_ts"] == AMOD_8K["published_ts"] and hit["items"] == "2.01,8.01"
        assert issuance.reason(hit) == ("Shares were issued per the SEC 8-K of Oct 1 11:30 ET (Items 2.01, 8.01): "
                                        "Yahoo's float and share count predate it. A warning only: no gate reads it")
        row = issuance.stamp({"symbol": "AMOD", "float": 630_935})
        assert row["shares_issued"] == hit and row["shares_issued_reason"] == issuance.reason(hit)
        assert issuance.stamp({"symbol": "ZZZ"})["shares_issued"] is None
        assert issuance.refresh(NOW + 31 * 86400, db) == 0      # older than the look-back: off the map
        assert issuance.for_symbol("AMOD") is None
    finally:
        issuance.reset_for_testing()
        db.close()


def test_the_trader_float_row_warns_and_never_blocks():
    from catalysts import issuance
    from stock_read.rows import float_rows

    hit = {"published_ts": AMOD_8K["published_ts"], "source": "edgar", "form": "8-K", "items": "2.01,8.01",
           "title": AMOD_8K["title"], "url": None}
    rows = {r["id"]: r for r in float_rows({"why": {"facts": {
        "float_shares": 630_935, "volume": 51_700_000, "shares_issued": hit}}})}
    assert (rows["float"]["value"], rows["float"]["state"]) == ("630.9K?", "warn")
    assert rows["float"]["detail"] == issuance.reason(hit)
    assert rows["rotation"]["value"] == "81.9x today?" and rows["rotation"]["state"] == "info"


@pytest.mark.parametrize("items, summary, issued", [
    ("3.02", "Item 3.02. Unregistered Sales of Equity Securities. The Company issued 2,000,000 shares.", True),
    ("2.01,9.01", "Item 2.01. Completion of Acquisition. The Company completed the acquisition of Widget LLC for "
                  "$5 million in cash.", False),
    ("8.01", "Item 8.01. Other Events. The Company issued a press release.", False),
])
def test_shares_issued(items, summary, issued):
    filing = {"source": "edgar", "form": "8-K", "sec_items": items, "title": "8-K: x", "summary": summary,
              "published_ts": NOW - 60}
    assert (shares_issued([filing], start=0, end=NOW) is not None) is issued


# -- the research store, counted the same way ----------------------------------------------------------------
RESEARCH = Path(__file__).resolve().parents[2] / "research" / "catalysts"


def test_recount_rewrites_stored_alpaca_rows(tmp_path):
    if str(RESEARCH) not in sys.path:
        sys.path.insert(0, str(RESEARCH))
    import fetch_alpaca
    import store

    con = store.connect(tmp_path / "catalysts.sqlite3")
    store.put_items(con, [
        {"item_id": "alpaca:62126197", "source": "alpaca", "published_ts": 1.0, "title": REWRITE["headline"],
         "tickers": ["AMOD", "BTCUSD"]},                     # stored before v8: n_tickers 2
        {"item_id": "alpaca:1", "source": "alpaca", "published_ts": 1.0, "title": "x", "tickers": ["AAPL", "MSFT"]},
    ])
    assert fetch_alpaca.recount(con) == 1
    assert dict(con.execute("SELECT item_id, n_tickers FROM items")) == {"alpaca:62126197": 1, "alpaca:1": 2}
    assert fetch_alpaca.recount(con) == 0
