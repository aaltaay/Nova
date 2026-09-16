"""Nasdaq Trade Halt RSS parse: match / miss / HTML ignored / MWCB."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ibkr.nasdaq_halt_rss import (
    RSS_HALTDATE_PARAM,
    RSS_URL,
    RSS_URL_HTTP,
    mwcb_level,
    parse_et_datetime,
    parse_trade_halt_rss,
)

FIXTURE = Path(__file__).with_name("fixtures") / "nasdaq_trade_halts.xml"
ET = ZoneInfo("America/New_York")


def _xml() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_documented_feed_urls_are_official_rss_not_html():
    assert RSS_URL.endswith("rss.aspx?feed=tradehalts")
    assert "nasdaqtrader.com" in RSS_URL
    assert RSS_URL_HTTP.startswith("http://")
    assert RSS_HALTDATE_PARAM == "haltdate"
    assert "trader.aspx" not in RSS_URL


def test_parse_luld_row_from_namespaced_children():
    parsed = parse_trade_halt_rss(_xml())
    assert parsed["ok"] is True
    by_sym = {row.symbol: row for row in parsed["rows"]}
    ztg = by_sym["ZTG"]
    assert ztg.reason_code == "LUDP"
    assert ztg.pause_threshold == "4.25"
    expected = datetime(2026, 9, 16, 10, 30, 0, tzinfo=ET).timestamp()
    assert ztg.official_halt_start == expected
    assert ztg.quote_resume == datetime(2026, 9, 16, 10, 35, 0, tzinfo=ET).timestamp()
    assert ztg.trade_resume == datetime(2026, 9, 16, 10, 40, 0, tzinfo=ET).timestamp()


def test_parse_news_row_has_no_invented_resume():
    parsed = parse_trade_halt_rss(_xml())
    news = {row.symbol: row for row in parsed["rows"]}["NEWS1"]
    assert news.reason_code == "T1"
    assert news.pause_threshold is None
    assert news.quote_resume is None
    assert news.trade_resume is None
    assert news.official_halt_start == datetime(
        2026, 9, 16, 10, 10, 0, tzinfo=ET,
    ).timestamp()


def test_plaintext_description_variant_is_accepted():
    parsed = parse_trade_halt_rss(_xml())
    plain = {row.symbol: row for row in parsed["rows"]}["PLAIN"]
    assert plain.reason_code == "T12"
    assert plain.trade_resume is None
    assert plain.quote_resume == datetime(2026, 9, 16, 11, 5, 0, tzinfo=ET).timestamp()


def test_html_description_table_is_not_scraped():
    parsed = parse_trade_halt_rss(_xml())
    by_sym = {row.symbol: row for row in parsed["rows"]}
    assert "FAKE" not in by_sym
    table = by_sym.get("TABLEONLY")
    if table is not None:
        assert table.reason_code is None
        assert table.trade_resume is None
        assert table.pause_threshold is None


def test_aapl_is_a_miss_in_the_recorded_fixture():
    parsed = parse_trade_halt_rss(_xml())
    assert all(row.symbol != "AAPL" for row in parsed["rows"])


def test_mwcb_level_2_from_reason_code_not_symbol_tier():
    parsed = parse_trade_halt_rss(_xml())
    assert parsed["mwcb"] == {
        "level": 2,
        "reason_code": "MWC2",
        "source": "nasdaq_trade_halt_rss",
    }
    assert mwcb_level("MWC1") == 1
    assert mwcb_level("MWC3") == 3
    assert mwcb_level("LUDP") is None
    assert mwcb_level("T1") is None


def test_mwc0_and_mwcq_are_not_level_banners():
    assert mwcb_level("MWC0") is None
    assert mwcb_level("MWCQ") is None


def test_empty_or_invalid_xml_fails_loud_without_rows():
    empty = parse_trade_halt_rss("")
    assert empty["ok"] is False
    assert empty["rows"] == []
    assert empty["mwcb"] is None
    bad = parse_trade_halt_rss("<not-rss")
    assert bad["ok"] is False
    assert bad["rows"] == []
    html = parse_trade_halt_rss("<html>halt page</html>")
    assert html["ok"] is False
    assert html["error"] == "not_rss"


def test_parse_et_datetime_refuses_incomplete_pairs():
    assert parse_et_datetime(None, "10:30:00") is None
    assert parse_et_datetime("09/16/2026", None) is None
    assert parse_et_datetime("09/16/2026", "not-a-time") is None
    assert parse_et_datetime("09/16/2026", "10:30:00.256") == datetime(
        2026, 9, 16, 10, 30, 0, tzinfo=ET,
    ).timestamp()
