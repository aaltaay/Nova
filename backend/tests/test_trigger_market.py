"""Where each ticker of the squares stands now (operator ask, 2026-10-12): ``market`` on ``GET /api/bot/triggers``.

The ticker's scanner row when a board holds it, priced by the L1 line's last trade, else the L1 line alone;
IBKR's prior close before the first trade is no change, and a ticker nothing holds says why. A past day and
a Sim replay desk carry no change.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from bot import trigger_market
from bot.trigger_cells import Context
from bot.trigger_timeline import Timeline
from main import app

client = TestClient(app)
TRADED = {"price": 3.0, "prev_close": 2.0, "quote_quality": "live", "last_trade_ts": 1.0, "volume": 1000}


def test_a_board_row_priced_by_the_lines_last_trade():
    row = {"symbol": "AISP", "price": 2.5, "prev_close": 2.0, "change_pct": 0.25}
    move = trigger_market.one("AISP", row, "gainers", TRADED)
    assert move == {"price": 3.0, "change_pct": 0.5, "change_abs": 1.0, "source": "gainers", "why": None}


def test_a_board_row_with_no_line_keeps_the_boards_change():
    row = {"symbol": "AISP", "price": 2.5, "prev_close": 2.0, "change_pct": 0.25}
    move = trigger_market.one("AISP", row, "gappers", None)
    assert move == {"price": 2.5, "change_pct": 0.25, "change_abs": 0.5, "source": "gappers", "why": None}


def test_a_ticker_off_every_board_reads_its_line():
    move = trigger_market.one("DCX", None, None, {**TRADED, "price": 1.5})
    assert move == {"price": 1.5, "change_pct": -0.25, "change_abs": -0.5, "source": "quote", "why": None}


def test_the_prior_close_before_the_first_trade_is_no_change():
    fallback = {"price": 2.0, "prev_close": 2.0, "quote_quality": "close_fallback", "last_trade_ts": None}
    move = trigger_market.one("AISP", None, None, fallback)
    assert move["change_pct"] is None and move["source"] == "quote" and "no trade on AISP yet" in move["why"]
    row = {"symbol": "AISP", "price": 2.0, "prev_close": 2.0, "change_pct": 0.0, "quote_quality": "close_fallback"}
    move = trigger_market.one("AISP", row, "gainers", fallback)
    assert move["change_pct"] is None and "IBKR's prior close" in move["why"]
    assert trigger_market.one("AISP", row, "gainers", TRADED)["change_pct"] == 0.5    # a trade since: it moved


def test_a_ticker_nothing_holds_says_why():
    move = trigger_market.one("ZZZZ", None, None, None)
    assert move["change_pct"] is None and move["why"] == \
        "no scanner board holds ZZZZ and Nova holds no Level 1 line on it"


def test_today_s_table_carries_each_tickers_move(monkeypatch):
    from ibkr import ticks
    from strategy import symbol_pillars
    from tests.bot_helpers import list_hot, on_practice

    on_practice()
    list_hot("AISP", "DCX")
    monkeypatch.setattr(symbol_pillars, "raw_boards", lambda: {
        "gainers": [{"symbol": "AISP", "price": 2.5, "prev_close": 2.0, "change_pct": 0.25}]})
    monkeypatch.setattr(ticks, "last_quotes", lambda syms: {"DCX": {**TRADED, "price": 1.5}})
    res = client.get("/api/bot/triggers")
    assert res.status_code == 200, res.text
    moves = {t["symbol"]: t["market"] for t in res.json()["tickers"]}
    assert moves["AISP"]["change_pct"] == 0.25 and moves["AISP"]["source"] == "gainers"
    assert moves["DCX"]["change_pct"] == -0.25 and moves["DCX"]["source"] == "quote"


def test_a_replay_desk_says_no_change(monkeypatch):
    from sim import mode

    monkeypatch.setattr(mode, "is_replay_desk", lambda: True)
    move = trigger_market.moves(["AISP"])["AISP"]
    assert move["change_pct"] is None and "Sim replay" in move["why"]


def test_a_past_day_carries_no_move():
    from bot import trigger_audit

    ctx = Context(timeline=Timeline([]), rules={}, listed={"AISP": {"how": "star", "at": 1.0}})
    body = trigger_audit.build("2026-09-30", lines=[], ctx=ctx, sources={}, generated_at=1.0)
    assert body["tickers"][0]["market"] is None
