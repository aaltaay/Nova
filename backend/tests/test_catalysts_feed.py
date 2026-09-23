"""The live catalyst feed (ADR 024): parsers, proven coverage, the store, and the live verdict."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import format_datetime

import pytest

from catalysts import feed as feed_mod
from catalysts import feed_sources, feed_store, live
from catalysts.feed import CatalystFeed
from constants_catalysts import CATALYST_FEED_EDGAR_FORMS, CATALYST_FEED_NEWSFILE_INDUSTRIES

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
    polled = [u for u in seen if "browse-edgar" in u]
    assert len(polled) == len(CATALYST_FEED_EDGAR_FORMS) and any("SC%20TO-T" in u for u in polled)


def test_the_store_refuses_an_unknown_version(tmp_path):
    db = feed_store.connect(tmp_path / "v.sqlite3")
    db.execute("PRAGMA user_version = 9")
    db.close()
    with pytest.raises(feed_store.FeedStoreVersionError):
        feed_store.connect(tmp_path / "v.sqlite3")
