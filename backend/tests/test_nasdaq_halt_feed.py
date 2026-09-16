"""Nasdaq Trade Halt RSS cache: poll cadence, match/miss, down, MWCB banner."""
from __future__ import annotations

from pathlib import Path

from constants import NASDAQ_TRADE_HALT_RSS_POLL_SEC
from ibkr import nasdaq_halt_feed
from ibkr.nasdaq_halt_rss import RSS_URL

FIXTURES = Path(__file__).with_name("fixtures")


def setup_function(_fn):
    nasdaq_halt_feed.reset()


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_poll_interval_is_at_least_one_minute():
    assert NASDAQ_TRADE_HALT_RSS_POLL_SEC >= 60.0
    assert "rss.aspx" in RSS_URL


def test_refresh_from_fixture_matches_and_misses():
    result = nasdaq_halt_feed.refresh(
        now=100.0, xml_text=_load("nasdaq_trade_halts.xml"),
    )
    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["mwcb"]["level"] == 2
    assert result["mwcb"]["stale"] is False
    hit = nasdaq_halt_feed.overlay_for("ztg")
    assert hit["matched"] is True
    assert hit["status"] == "ok"
    assert hit["reason_code"] == "LUDP"
    miss = nasdaq_halt_feed.overlay_for("AAPL")
    assert miss["matched"] is False
    assert miss["status"] == "pending"
    assert miss["trade_resume"] is None
    assert miss["quote_resume"] is None
    assert miss["official_halt_start"] is None


def test_second_fetch_inside_ttl_is_skipped_without_calling_network():
    nasdaq_halt_feed.refresh(now=100.0, xml_text=_load("nasdaq_trade_halts.xml"))

    def boom() -> str:
        raise AssertionError("must not poll Nasdaq more than once per minute")

    skipped = nasdaq_halt_feed.refresh(now=130.0, fetch=boom)
    assert skipped["skipped"] is True
    assert skipped["reason"] == "poll_interval"
    later = nasdaq_halt_feed.refresh(
        now=160.0, xml_text=_load("nasdaq_trade_halts_empty.xml"),
    )
    assert later["skipped"] is False
    assert later["ok"] is True
    assert nasdaq_halt_feed.overlay_for("ZTG")["matched"] is False
    assert later["mwcb"] is None


def test_failed_fetch_marks_down_and_does_not_invent_resume():
    nasdaq_halt_feed.refresh(now=10.0, xml_text=_load("nasdaq_trade_halts.xml"))

    def fail() -> str:
        raise OSError("nasdaq unreachable")

    down = nasdaq_halt_feed.refresh(now=80.0, fetch=fail)
    assert down["ok"] is False
    assert down["feed"]["status"] == "down"
    # Last good rows stay so IBKR+clock can keep overlaying official times
    # already learned; a never-seen symbol stays pending/down with no times.
    known = nasdaq_halt_feed.overlay_for("ZTG")
    assert known["matched"] is True
    assert known["trade_resume"] is not None
    unknown = nasdaq_halt_feed.overlay_for("MSFT")
    assert unknown["matched"] is False
    assert unknown["status"] == "down"
    assert unknown["trade_resume"] is None
    assert down["mwcb"]["stale"] is True


def test_invalid_xml_is_down_not_empty_success():
    result = nasdaq_halt_feed.refresh(now=1.0, xml_text="<html>halt page</html>")
    assert result["ok"] is False
    assert result["feed"]["status"] == "down"
    assert nasdaq_halt_feed.overlay_for("ZTG")["trade_resume"] is None


def test_mwcb_clears_on_successful_feed_without_codes():
    nasdaq_halt_feed.refresh(now=10.0, xml_text=_load("nasdaq_trade_halts_mwc1.xml"))
    assert nasdaq_halt_feed.desk_snapshot()["mwcb"]["level"] == 1
    nasdaq_halt_feed.refresh(now=80.0, xml_text=_load("nasdaq_trade_halts_empty.xml"))
    assert nasdaq_halt_feed.desk_snapshot()["mwcb"] is None


def test_empty_successful_feed_is_empty_not_down():
    result = nasdaq_halt_feed.refresh(
        now=1.0, xml_text=_load("nasdaq_trade_halts_empty.xml"),
    )
    assert result["ok"] is True
    assert result["feed"]["status"] == "empty"


def test_refresh_utf8_bom_body_is_ok_not_down():
    raw = (FIXTURES / "nasdaq_trade_halts_bom.xml").read_bytes()
    # Live Ahmed desk: requests.text latin-1 of EF BB BF -> column-1 invalid token.
    result = nasdaq_halt_feed.refresh(now=1.0, xml_text=raw.decode("latin-1"))
    assert result["ok"] is True, result.get("feed", {}).get("error")
    assert result["feed"]["status"] == "ok"
    assert result["feed"]["error"] is None
    hit = nasdaq_halt_feed.overlay_for("ZTG")
    assert hit["matched"] is True
    assert hit["status"] == "ok"
    assert hit["reason_code"] == "LUDP"
    miss = nasdaq_halt_feed.overlay_for("QCLS")
    assert miss["matched"] is False
    assert miss["trade_resume"] is None


def test_default_fetch_is_not_used_when_xml_injected():
    def boom() -> str:
        raise AssertionError("CI must not hit live Nasdaq")

    nasdaq_halt_feed.refresh(
        now=1.0, xml_text=_load("nasdaq_trade_halts.xml"), fetch=boom,
    )
    assert nasdaq_halt_feed.overlay_for("NEWS1")["reason_code"] == "T1"
