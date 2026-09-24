"""The live catalyst feed (ADR 024): parsers, proven coverage, the store, and the live verdict."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import pytest

from catalysts import feed as feed_mod
from catalysts import feed_sources, feed_store, live
from catalysts.feed import CatalystFeed
from constants_catalysts import (
    CATALYST_FEED_EDGAR_FORMS,
    CATALYST_FEED_FORM4_MAX_ATTEMPTS,
    CATALYST_FEED_FORM4_MAX_PAGES,
    CATALYST_FEED_NEWSFILE_INDUSTRIES,
)

T0 = 1_790_000_000.0


def rss(items, *, gnw=False):
    body = []
    for title, ts, extra in items:
        cat = f'<category domain="https://www.globenewswire.com/rss/stock">{extra}</category>' if gnw and extra else ""
        desc = extra if not gnw else ""
        body.append(f"<item><title>{title}</title><link>https://wire/{title.replace(' ', '-')}</link>{cat}"
                    f"<description>{desc}</description>"
                    f"<pubDate>{format_datetime(datetime.fromtimestamp(ts, timezone.utc))}</pubDate></item>")
    return f'<?xml version="1.0"?><rss><channel><title>t</title>{"".join(body)}</channel></rss>'.encode()


def atom(entries):
    body = []
    for form, cik, acc, ts, items in entries:
        iso = datetime.fromtimestamp(ts, timezone.utc).isoformat()
        summ = "&lt;b&gt;AccNo:&lt;/b&gt; " + acc + "".join(f"&lt;br&gt;Item {i}: x" for i in items)
        body.append(f"<entry><title>{form} - ACME INC ({int(cik):010d}) (Filer)</title>"
                    f'<link href="https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-", "")}/{acc}-index.htm"/>'
                    f'<summary type="html">{summ}</summary><updated>{iso}</updated>'
                    f"<id>urn:tag:sec.gov,2008:accession-number={acc}</id></entry>")
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{"".join(body)}</feed>'.encode()


def test_tickers_are_read_from_tags_and_text():
    assert feed_sources.tickers_in("Acme (NASDAQ: ABCD) and (NYSE American: XYZ, XYZ.WS) (TSXV: NOPE)") == ["ABCD", "XYZ", "XYZ.WS"]
    items = feed_sources.parse_rss(rss([("Angi Appoints CEO", T0, "Nasdaq:ANGI")], gnw=True), "globenewswire")
    assert items[0]["tickers"] == ["ANGI"]
    atom_rows = feed_sources.parse_edgar_atom(atom([("8-K", "918541", "0000918541-26-000093", T0, ["2.02", "9.01"])]))
    assert atom_rows[0]["cik"] == "918541" and atom_rows[0]["items"] == "2.02,9.01" and atom_rows[0]["accepted_ts"] == T0


def test_fda_names_match_only_long_full_names():
    names = {feed_sources.company_key("Capricor Therapeutics, Inc."): ["CAPR"], feed_sources.company_key("Ab Co"): ["AB"]}
    assert feed_sources.tickers_named("FDA approves therapy from Capricor Therapeutics for DMD", names) == ["CAPR"]
    assert feed_sources.tickers_named("FDA grants a lab co approval", names) == []


class FakeNet:
    def __init__(self):
        self.pages: dict[str, bytes] = {}

    def __call__(self, url, headers):
        for key, body in self.pages.items():
            if key in url:
                return body
        if "company_tickers" in url:
            return json.dumps({"0": {"cik_str": 918541, "ticker": "ACME", "title": "Acme Inc"}}).encode()
        if "browse-edgar" in url:
            return atom([])
        if "newsfilecorp" in url:
            return rss([])
        raise OSError(f"no page for {url}")


@pytest.fixture
def net(monkeypatch):
    fake = FakeNet()
    monkeypatch.setattr(feed_mod.time, "sleep", lambda s: None)
    return fake


def make_feed(net, clock, tmp_path):
    f = CatalystFeed(fetch=net, clock=lambda: clock["t"], db=feed_store.connect(tmp_path / "feed.sqlite3"))
    f.warm_start()
    return f


def test_a_wire_span_extends_only_while_the_feed_reaches_back(net, tmp_path):
    clock = {"t": T0}
    net.pages["globenewswire"] = rss([("Acme Wins Contract", T0 - 30, "Nasdaq:ACME"), ("Old", T0 - 900, "Nasdaq:ZZZ")], gnw=True)
    f = make_feed(net, clock, tmp_path)
    f.tick()
    assert f.status()["sources"]["globenewswire"]["covering_since"] == T0 - 900   # the page reaches back
    clock["t"] = T0 + 60
    net.pages["globenewswire"] = rss([("New", T0 + 50, "Nasdaq:NEW"), ("Acme Wins Contract", T0 - 30, "Nasdaq:ACME")], gnw=True)
    f.tick()
    assert "globenewswire" in f.covered_sources(T0 - 800, T0 + 60)
    # A burst: the whole page is newer than the last poll -- something may have been missed.
    clock["t"] = T0 + 120
    net.pages["globenewswire"] = rss([("B1", T0 + 115, "Nasdaq:B"), ("B2", T0 + 110, "Nasdaq:B")], gnw=True)
    f.tick()
    assert "globenewswire" not in f.covered_sources(T0 - 800, T0 + 120)
    assert f.sources["globenewswire"].gaps == 1


def test_edgar_filings_carry_their_release_and_ticker(net, tmp_path):
    clock = {"t": T0}
    acc = "0000918541-26-000093"
    net.pages["type=8-K&"] = atom([("8-K", "918541", acc, T0 - 60, ["8.01", "9.01"])])
    net.pages["/index.json"] = json.dumps({"directory": {"item": [{"name": "ex99-1.htm"}]}}).encode()
    net.pages["ex99-1.htm"] = b"<p>Exhibit 99.1</p><p>Acme Receives FDA Approval for Widget in Adults</p><p>Acme today announced ...</p>"
    f = make_feed(net, clock, tmp_path)
    f.tick()
    items = f.items_for("ACME", T0 - 3600, T0)
    assert items and items[0]["source"] == "edgar" and "FDA Approval" in items[0]["title"]
    assert "edgar" in f.covered_sources(T0 - 60, T0)
    # A restart reloads the morning from the store.
    g = make_feed(net, clock, tmp_path)
    assert g.items_for("ACME", T0 - 3600, T0)


def test_newsfile_rotation_extends_after_a_clean_round(net, tmp_path):
    clock = {"t": T0}
    f = make_feed(net, clock, tmp_path)
    step = f.sources["newsfile"].interval / len(CATALYST_FEED_NEWSFILE_INDUSTRIES)
    for _ in range(len(CATALYST_FEED_NEWSFILE_INDUSTRIES)):
        f.tick()
        clock["t"] += step + 0.01
    first_round_done = f.sources["newsfile"].span[0]      # coverage starts once every industry was read
    assert "newsfile" not in f.covered_sources(T0, clock["t"])
    for _ in range(len(CATALYST_FEED_NEWSFILE_INDUSTRIES)):
        f.tick()
        clock["t"] += step + 0.01
    assert "newsfile" in f.covered_sources(first_round_done, clock["t"])


def test_one_failing_source_does_not_stop_the_others(net, tmp_path):
    clock = {"t": T0}
    net.pages["globenewswire"] = rss([("Acme Wins Contract", T0 - 30, "Nasdaq:ACME")], gnw=True)
    f = make_feed(net, clock, tmp_path)
    f.tick()   # prnewswire / fda have no page: they fail, GlobeNewswire still records
    assert f.sources["prnewswire"].last_error and f.items_for("ACME", T0 - 60, T0)


def test_the_live_verdict_uses_the_feed_and_flags_a_news_pending_halt(net, tmp_path, monkeypatch):
    clock = {"t": T0}
    net.pages["globenewswire"] = rss([("Acme Receives FDA Approval for Widget", T0 - 30, "Nasdaq:ACME"),
                                      ("Old", live.window_start(T0) - 60, "Nasdaq:ZZZ")], gnw=True)
    f = make_feed(net, clock, tmp_path)
    f.tick()
    monkeypatch.setattr(feed_mod, "_feed", f)
    live.reset_for_testing()
    v = live.verdict_for("ACME", T0)
    assert v["verdict"] == "catalyst" and v["source"] == "globenewswire" and "globenewswire" in v["sources_answered"]
    assert live.verdict_for("QUIET", T0)["verdict"] == "none_found"     # the wire covered the window and named nothing

    from ibkr import nasdaq_halt_feed
    monkeypatch.setattr(nasdaq_halt_feed, "overlay_for", lambda sym: {
        "reason_code": "T1", "official_halt_start": T0 - 10, "trade_resume": None})
    q = live.verdict_for("QUIET", T0)
    assert q["news_pending"] is True and q["halt_code"] == "T1"


def test_every_edgar_form_is_polled(net, tmp_path):
    seen = []
    clock = {"t": T0}

    def fetch(url, headers):
        seen.append(url)
        return net(url, headers)

    f = CatalystFeed(fetch=fetch, clock=lambda: clock["t"], db=feed_store.connect(tmp_path / "f.sqlite3"))
    f.warm_start()
    f.tick()
    polled = [u for u in seen if "browse-edgar" in u and "owner=only" not in u]
    assert len(polled) == len(CATALYST_FEED_EDGAR_FORMS) and any("SC%20TO-T" in u for u in polled)
    assert [u for u in seen if "owner=only" in u and "type=4&" in u]      # Form 4 is its own source (#517)


def test_the_store_refuses_an_unknown_version(tmp_path):
    db = feed_store.connect(tmp_path / "v.sqlite3")
    db.execute("PRAGMA user_version = 9")
    db.close()
    with pytest.raises(feed_store.FeedStoreVersionError):
        feed_store.connect(tmp_path / "v.sqlite3")


# -- the Form 4 source (#517) --------------------------------------------------------------------
FORM4 = Path(__file__).parent / "fixtures" / "form4"
BFRG_CIK, ACME_CIK = "1829247", "918541"
BFRG_ACC = "0001829247-26-000061"


def atom4(entries):
    """EDGAR's latest Form 4s: ``(acc, ts, cik, role, name)`` -- a filing is listed once per party."""
    body = []
    for acc, ts, cik, role, name in entries:
        iso = datetime.fromtimestamp(ts, timezone.utc).isoformat()
        body.append(f"<entry><title>4 - {name} ({int(cik):010d}) ({role})</title>"
                    f'<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/{cik}/'
                    f'{acc.replace("-", "")}/{acc}-index.htm"/>'
                    f'<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; 2026-09-22 &lt;b&gt;AccNo:&lt;/b&gt; {acc} '
                    f"&lt;b&gt;Size:&lt;/b&gt; 5 KB</summary><updated>{iso}</updated>"
                    f'<category scheme="https://www.sec.gov/" label="form type" term="4"/>'
                    f"<id>urn:tag:sec.gov,2008:accession-number={acc}</id></entry>")
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{"".join(body)}</feed>'.encode()


def filing(acc, ts, issuer_cik, issuer="ACME INC", owner_cik="9990001"):
    return [(acc, ts, owner_cik, "Reporting", "Example Owner"), (acc, ts, issuer_cik, "Issuer", issuer)]


class Recorder:
    def __init__(self, net):
        self.net, self.urls = net, []

    def __call__(self, url, headers):
        self.urls.append(url)
        return self.net(url, headers)

    def reads(self, acc):
        return sum(1 for u in self.urls if u.endswith(f"/{acc}.txt"))


def form4_feed(net, clock, tmp_path):
    net.pages["company_tickers"] = json.dumps({"0": {"cik_str": 918541, "ticker": "ACME", "title": "Acme Inc"},
                                               "1": {"cik_str": 1829247, "ticker": "BFRG",
                                                     "title": "BullFrog AI Holdings, Inc."}}).encode()
    rec = Recorder(net)
    f = CatalystFeed(fetch=rec, clock=lambda: clock["t"], db=feed_store.connect(tmp_path / "feed.sqlite3"))
    f.warm_start()
    return f, rec


def test_form4_keeps_an_insiders_purchase_from_the_issuer_entry_and_lets_the_rest_go(net, tmp_path):
    clock = {"t": T0}
    net.pages["owner=only"] = atom4(
        filing(BFRG_ACC, T0 - 100, BFRG_CIK, "BullFrog AI Holdings, Inc.")
        + filing("0000918541-26-000002", T0 - 200, ACME_CIK)                    # a 10% holder's buy: not management
        + filing("0007777777-26-000003", T0 - 300, "7777777", "UNLISTED CO"))  # no ticker: never fetched
    net.pages[f"{BFRG_ACC}.txt"] = FORM4.joinpath("bfrg_ceo_purchase.txt").read_bytes()
    net.pages["0000918541-26-000002.txt"] = FORM4.joinpath("ten_percent_owner_purchase.xml").read_bytes()
    f, rec = form4_feed(net, clock, tmp_path)
    f.tick()
    (item,) = f.items_for("BFRG", T0 - 3600, T0)
    assert (item["source"], item["form"], item["sec_items"], item["tickers"]) == ("edgar", "4", "P:57225", ["BFRG"])
    assert item["title"].startswith("Form 4: open-market purchase by Example Chief (CEO, Director)")
    assert item["url"].endswith(f"{BFRG_ACC}-index.htm")
    assert f"/data/{BFRG_CIK}/{BFRG_ACC.replace('-', '')}/{BFRG_ACC}.txt" in " ".join(rec.urls)
    assert f.items_for("ACME", T0 - 3600, T0) == []
    assert (rec.reads(BFRG_ACC), rec.reads("0000918541-26-000002"), rec.reads("0007777777-26-000003")) == (1, 1, 0)
    src = f.status()["sources"]["edgar_form4"]
    assert (src["items"], src["covering_since"], src["last_error"]) == (1, T0 - 300, None)
    # Its span is its own; it names a purchase, never "no news", so it is not a coverage source.
    assert "edgar_form4" not in f.covered_sources(T0 - 300, T0)
    clock["t"] = T0 + 60
    f.tick()                                           # both filings were read: neither is fetched again
    assert (rec.reads(BFRG_ACC), rec.reads("0000918541-26-000002")) == (1, 1)
    assert f.sources["edgar_form4"].span == [T0 - 300, T0 + 60]
    # A restart reloads the purchase, stamp included.
    g, _ = form4_feed(net, clock, tmp_path)
    assert g.items_for("BFRG", T0 - 3600, T0)[0]["sec_items"] == "P:57225"


def test_a_form4_burst_breaks_its_own_span_and_never_edgars(net, tmp_path):
    clock = {"t": T0}
    net.pages["type=8-K&"] = atom([("8-K", "918541", "0000918541-26-000093", T0 - 60, ["7.01"])])
    net.pages["owner=only"] = atom4(filing("0000918541-26-000010", T0 - 100, "7777777", "UNLISTED CO"))
    f, rec = form4_feed(net, clock, tmp_path)
    f.tick()
    assert f.sources["edgar_form4"].span == [T0 - 100, T0] and f.sources["edgar"].span == [T0 - 60, T0]
    # Every page EDGAR can list is newer than the last poll: Form 4s may have been missed in between.
    clock["t"] = T0 + 60
    net.pages["owner=only"] = atom4([(f"0000000001-26-{n:06d}", T0 + 30, "9990001", "Reporting", "Example Owner")
                                     for n in range(100)])
    rec.urls.clear()
    f.tick()
    assert sum(1 for u in rec.urls if "owner=only" in u) == CATALYST_FEED_FORM4_MAX_PAGES
    assert f.sources["edgar_form4"].gaps == 1 and f.sources["edgar_form4"].span == [T0 + 30, T0 + 60]
    assert f.sources["edgar"].gaps == 0 and "edgar" in f.covered_sources(T0 - 60, T0 + 60)


def test_a_form4_nobody_could_read_breaks_the_span_there(net, tmp_path):
    clock = {"t": T0}
    listed = filing("0000000001-26-000001", T0 - 100, "7777777", "UNLISTED CO")
    net.pages["owner=only"] = atom4(listed)
    f, rec = form4_feed(net, clock, tmp_path)
    f.tick()
    assert f.sources["edgar_form4"].span == [T0 - 100, T0]
    # Accepted before the last poll but listed only now (EDGAR's dissemination lag), and never fetchable.
    lost = "0000918541-26-000099"
    net.pages["owner=only"] = atom4(filing(lost, T0 - 10, ACME_CIK) + listed)
    for n in range(1, CATALYST_FEED_FORM4_MAX_ATTEMPTS):
        clock["t"] = T0 + 60 * n
        f.tick()
        assert f.sources["edgar_form4"].span == [T0 - 100, T0]     # retried; never extended past an unread filing
    clock["t"] = T0 + 60 * CATALYST_FEED_FORM4_MAX_ATTEMPTS
    f.tick()                                                       # given up: a known miss
    assert rec.reads(lost) == CATALYST_FEED_FORM4_MAX_ATTEMPTS
    assert f.sources["edgar_form4"].gaps == 1
    assert (T0 - 100, T0 - 11) in f._spans["edgar_form4"]          # the old span ends before the miss ...
    assert f.sources["edgar_form4"].span == [T0 - 10, clock["t"]]  # ... and the new one opens at it
    assert ("edgar_form4", T0 - 100, T0 - 11) in feed_store.spans_since(f._db, 0)
    clock["t"] += 60
    f.tick()
    assert rec.reads(lost) == CATALYST_FEED_FORM4_MAX_ATTEMPTS and f.sources["edgar_form4"].gaps == 1


def test_bfrg_the_live_verdict_names_the_insider_buy(net, tmp_path, monkeypatch):
    """#517: BFRG ran +24% premarket on 2026-09-23 on two Form 4s filed at 16:45 ET the evening before; the
    only article was a movers piece, and the verdict was ``noise_only``."""
    filed = datetime(2026, 9, 22, 20, 45, 2, tzinfo=timezone.utc).timestamp()     # 16:45:02 ET
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc).timestamp()           # 08:00 ET
    clock = {"t": now}
    net.pages["owner=only"] = atom4(filing(BFRG_ACC, filed, BFRG_CIK, "BullFrog AI Holdings, Inc."))
    net.pages[f"{BFRG_ACC}.txt"] = FORM4.joinpath("bfrg_ceo_purchase.txt").read_bytes()
    f, _ = form4_feed(net, clock, tmp_path)
    f.tick()
    monkeypatch.setattr(feed_mod, "_feed", f)
    live.reset_for_testing()
    live.record(["BFRG"], [{"id": 1, "created_at": "2026-09-23T11:30:00Z", "symbols": ["BFRG"], "source": "benzinga",
                            "headline": "BullFrog AI Holdings Stock Climbs Over 24% Pre-Market: "
                                        "Here's What You Need to Know",
                            "url": "https://www.benzinga.com/trading-ideas/movers/26/09/1/"
                                   "bullfrog-ai-bfrg-stock-jumps-premarket-ceo-cfo-insider-buying"}],
                start=live.window_start(now), through=now)
    v = live.verdict_for("BFRG", now)
    assert (v["verdict"], v["category"], v["strength"], v["source"]) == ("catalyst", "listing_financing", "weak", "edgar")
    assert v["title"].startswith("Form 4: open-market purchase") and v["n_items"] == 2
    live.reset_for_testing()
