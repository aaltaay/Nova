"""Nasdaq Trade Halt RSS parse: match / miss / HTML ignored / MWCB."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ibkr.nasdaq_halt_rss import (
    RSS_HALTDATE_PARAM,
    RSS_URL,
    RSS_URL_HTTP,
    HaltRssRow,
    better_overlay_row,
    mwcb_level,
    parse_et_datetime,
    parse_trade_halt_rss,
    prepare_rss_xml,
)

FIXTURES = Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "nasdaq_trade_halts.xml"
BOM_FIXTURE = FIXTURES / "nasdaq_trade_halts_bom.xml"
ET = ZoneInfo("America/New_York")
UTF8_BOM = b"\xef\xbb\xbf"


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


def test_bom_fixture_starts_with_utf8_bom_then_xml_decl():
    raw = BOM_FIXTURE.read_bytes()
    assert raw.startswith(UTF8_BOM + b"<?xml")
    assert raw[3:5] == b"<?"


def test_prepare_rss_xml_strips_bom_and_whitespace():
    raw = BOM_FIXTURE.read_bytes()
    clean = FIXTURE.read_text(encoding="utf-8").lstrip()
    assert prepare_rss_xml(raw).startswith("<?xml")
    assert prepare_rss_xml(raw.decode("utf-8")).startswith("<?xml")
    assert prepare_rss_xml(raw.decode("latin-1")).startswith("<?xml")
    assert prepare_rss_xml("\n\n  " + clean).startswith("<?xml")
    assert prepare_rss_xml(b"\xef\xbb\xbf") == ""


def test_parse_utf8_bom_fixture_succeeds():
    raw = BOM_FIXTURE.read_bytes()
    as_utf8 = raw.decode("utf-8")  # keeps U+FEFF, as utf-8 .text would
    parsed_bytes = parse_trade_halt_rss(raw)
    parsed_text = parse_trade_halt_rss(as_utf8)
    assert parsed_bytes["ok"] is True
    assert parsed_text["ok"] is True
    by_sym = {row.symbol: row for row in parsed_text["rows"]}
    assert by_sym["ZTG"].reason_code == "LUDP"
    assert by_sym["NEWS1"].trade_resume is None


def test_parse_latin1_mojibake_of_utf8_bom_matches_live_desk_error():
    """Nasdaq omits charset; requests.text is ISO-8859-1 -> ï»¿<?xml (live error)."""
    raw = BOM_FIXTURE.read_bytes()
    as_latin1 = raw.decode("latin-1")
    assert as_latin1.startswith("ï»¿<?xml")
    parsed = parse_trade_halt_rss(as_latin1)
    assert parsed["ok"] is True, parsed.get("error")
    assert parsed["error"] is None
    assert {row.symbol for row in parsed["rows"]} >= {"ZTG", "NEWS1"}


def test_parse_leading_whitespace_before_xml_decl():
    parsed = parse_trade_halt_rss("\n\n  " + _xml())
    assert parsed["ok"] is True
    assert {row.symbol for row in parsed["rows"]} >= {"ZTG"}


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


def _row(**kwargs) -> HaltRssRow:
    defaults = dict(
        symbol="DLXY",
        reason_code="LUDP",
        official_halt_start=100.0,
        pause_threshold=None,
        quote_resume=None,
        trade_resume=None,
        mwcb_level=None,
    )
    defaults.update(kwargs)
    return HaltRssRow(**defaults)


def test_better_overlay_row_prefers_open_then_newest_start():
    open_new = _row(official_halt_start=200.0, trade_resume=None)
    open_old = _row(official_halt_start=50.0, trade_resume=None)
    resumed_newer = _row(official_halt_start=300.0, trade_resume=400.0)
    resumed_older = _row(official_halt_start=10.0, trade_resume=20.0)
    assert better_overlay_row(resumed_newer, open_new) == open_new
    assert better_overlay_row(open_new, resumed_older) == open_new
    assert better_overlay_row(open_old, open_new) == open_new
    assert better_overlay_row(resumed_older, resumed_newer) == resumed_newer
