"""Live scanner rows state their halt (#487): true / false / null, never a guess."""
from __future__ import annotations

import asyncio
import json
import time

import pytest

import scanner_push
import scanner_surface
from constants import NASDAQ_TRADE_HALT_RSS_FRESH_SEC
from ibkr import client as ibkr_client
from ibkr import halt_status, nasdaq_halt_feed, ticks
from ibkr.nasdaq_halt_rss import parse_et_datetime
from runtime_state.state import TableState

DAY = "09/24/2026"


def _item(symbol: str, reason: str = "LUDP", halt: str = "10:00:00", resume: str = "", resume_day: str = DAY) -> str:
    return (
        f"<item><title>{symbol}</title><ndaq:HaltDate>{DAY}</ndaq:HaltDate>"
        f"<ndaq:HaltTime>{halt}</ndaq:HaltTime><ndaq:IssueSymbol>{symbol}</ndaq:IssueSymbol>"
        f"<ndaq:ReasonCode>{reason}</ndaq:ReasonCode>"
        f"<ndaq:ResumptionDate>{resume_day if resume else ''}</ndaq:ResumptionDate>"
        f"<ndaq:ResumptionTradeTime>{resume}</ndaq:ResumptionTradeTime></item>"
    )


def _rss(*items: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<rss version="2.0" xmlns:ndaq="http://www.nasdaqtrader.com/"><channel>'
        "<title>NASDAQTrader.com</title>" + "".join(items) + "</channel></rss>"
    )


def _mwcb() -> str:
    return (
        f"<item><title>Market Wide Circuit Breaker</title><ndaq:HaltDate>{DAY}</ndaq:HaltDate>"
        "<ndaq:HaltTime>09:45:00</ndaq:HaltTime><ndaq:IssueSymbol></ndaq:IssueSymbol>"
        "<ndaq:ReasonCode>MWC1</ndaq:ReasonCode></item>"
    )


class _Ticker:
    def __init__(self, halted) -> None:
        self.halted = halted


@pytest.fixture
def lines(monkeypatch):
    """Live IBKR L1 lines by symbol; the session is ready."""
    held: dict[str, _Ticker] = {}
    monkeypatch.setattr(ibkr_client, "is_ready", lambda: True)
    monkeypatch.setattr(ticks, "get_ticker", lambda s: held.get((s or "").upper()))
    return held


@pytest.fixture
def no_blocklist(monkeypatch):
    monkeypatch.setattr(scanner_surface._hod_momo, "is_blocked", lambda _s: False)


def test_the_feed_answers_open_resumed_and_unlisted():
    nasdaq_halt_feed.refresh(now=time.time(), xml_text=_rss(
        _item("HALT", "T1"),
        _item("DONE", resume="10:05:00", resume_day="09/16/2020"),
    ))
    got = halt_status.halted_now(["halt", "DONE", "QUIET"])
    assert got == {"HALT": True, "DONE": False, "QUIET": False}


def test_a_resumption_still_ahead_is_still_a_halt():
    resume = parse_et_datetime(DAY, "10:10:00")
    assert resume is not None
    nasdaq_halt_feed.refresh(now=resume - 60, xml_text=_rss(_item("PAUSE", resume="10:10:00")))
    assert halt_status.halted_now(["PAUSE"], now=resume - 60) == {"PAUSE": True}
    assert halt_status.halted_now(["PAUSE"], now=resume + 60) == {"PAUSE": False}


def test_no_answering_source_is_unknown():
    # Nothing read yet: pending.
    assert halt_status.halted_now(["ABC"]) == {"ABC": None}
    # A read that is too old no longer says anything is trading -- nor halted.
    then = time.time() - NASDAQ_TRADE_HALT_RSS_FRESH_SEC - 5
    nasdaq_halt_feed.refresh(now=then, xml_text=_rss(_item("HALT", "T1")))
    assert halt_status.halted_now(["ABC", "HALT"]) == {"ABC": None, "HALT": None}


def test_a_failed_read_is_not_an_answer():
    nasdaq_halt_feed.refresh(now=time.time() - 120, xml_text=_rss(_item("HALT", "T1")))

    def boom() -> str:
        raise OSError("down")

    nasdaq_halt_feed.refresh(now=time.time(), fetch=boom)
    assert nasdaq_halt_feed.desk_snapshot()["feed"]["status"] == "down"
    assert halt_status.halted_now(["ABC", "HALT"]) == {"ABC": None, "HALT": None}


def test_an_empty_feed_answers_not_halted():
    nasdaq_halt_feed.refresh(now=time.time(), xml_text=_rss())
    assert nasdaq_halt_feed.desk_snapshot()["feed"]["status"] == "empty"
    assert halt_status.halted_now(["ABC"]) == {"ABC": False}


def test_a_market_wide_circuit_breaker_leaves_nothing_reading_as_trading():
    nasdaq_halt_feed.refresh(now=time.time(), xml_text=_rss(_mwcb(), _item("HALT", "T1")))
    assert halt_status.halted_now(["ABC", "HALT"]) == {"ABC": None, "HALT": True}


def test_ibkr_tick_49_decides_where_nova_holds_a_line(lines):
    nasdaq_halt_feed.refresh(now=time.time(), xml_text=_rss(_item("RSSOPEN", "T1")))
    lines["LULD"] = _Ticker(2.0)
    lines["NEWS"] = _Ticker(1)
    lines["TRADE"] = _Ticker(0)
    # IBKR's own current flag wins over a Nasdaq row still open (the Level 2 header's rule).
    lines["RSSOPEN"] = _Ticker(0)
    # A line that has not reported (NaN) or says "not available" (-1) is no answer: the feed decides.
    lines["NOTYET"] = _Ticker(float("nan"))
    lines["UNAVAIL"] = _Ticker(-1)
    got = halt_status.halted_now(["LULD", "NEWS", "TRADE", "RSSOPEN", "NOTYET", "UNAVAIL"])
    assert got == {"LULD": True, "NEWS": True, "TRADE": False, "RSSOPEN": False, "NOTYET": False, "UNAVAIL": False}


def test_a_line_is_no_answer_while_the_session_is_not_ready(monkeypatch, lines):
    lines["TRADE"] = _Ticker(0)
    lines["LULD"] = _Ticker(2)
    monkeypatch.setattr(ibkr_client, "is_ready", lambda: False)
    assert halt_status.halted_now(["TRADE", "LULD"]) == {"TRADE": None, "LULD": None}


def test_surface_rows_stamp_halted_and_never_touch_the_cache(no_blocklist, lines):
    nasdaq_halt_feed.refresh(now=time.time(), xml_text=_rss(_item("HALT", "T1")))
    lines["LINE"] = _Ticker(0)
    cache = [{"symbol": "HALT", "price": 4.0}, {"symbol": "LINE", "price": 2.0}, {"symbol": "OTHER", "price": 1.0}]
    out = {r["symbol"]: r for r in scanner_surface.surface_rows(cache, "gainers")}
    assert out["HALT"]["halted"] is True
    assert out["LINE"]["halted"] is False
    assert out["OTHER"]["halted"] is False
    # A view over the row, never written into the cache (ADR 008).
    assert all("halted" not in row for row in cache)

    nasdaq_halt_feed.reset()
    out = {r["symbol"]: r for r in scanner_surface.surface_rows(cache, "large_cap")}
    assert out["LINE"]["halted"] is False
    assert out["OTHER"]["halted"] is None
    assert out["HALT"]["halted"] is None
    assert all("halted" not in row for row in cache)


def test_a_failed_halt_read_leaves_every_row_unknown(no_blocklist, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("no halt state")

    monkeypatch.setattr(scanner_surface._halt_status, "halted_now", boom)
    out = scanner_surface.surface_rows([{"symbol": "ABC", "price": 1.0}], "gainers")
    assert out[0]["halted"] is None


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.frames.append(json.loads(text))


def test_the_roster_push_carries_halted(no_blocklist, monkeypatch):
    nasdaq_halt_feed.refresh(now=time.time(), xml_text=_rss(_item("HALT", "T1")))
    sock = _FakeSocket()
    monkeypatch.setattr(scanner_push, "_clients", {sock})
    ts = TableState()
    ts.state = "live"
    asyncio.run(scanner_push.broadcast_roster_replace("gainers", [{"symbol": "HALT"}, {"symbol": "OK"}], ts))
    assert {r["symbol"]: r["halted"] for r in sock.frames[0]["rows"]} == {"HALT": True, "OK": False}
