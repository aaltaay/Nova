"""Bot fills on the audit stream (operator ask 2026-10-16; architecture/schema/bot.md, "Fills on the bot audit
stream"): a ``partial`` line each time a working bot order fills more shares, a ``fill`` block on ``filled``
lines, and one fixed set of outcome names for the bots' trade lines.

Paper and Sim fill an order whole, so the partials are a venue row faked over the real one.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from bot import fill_progress
from bot.audit import list_entries, record
from bot.first_pullback import orders as fp_orders
from bot.live_trader import act as lt_act
from bot.live_trader import book as lt_book
from bot.live_trader import orders as lt_orders
from constants_bot import BOT_TRADE_AUDIT_ACTIONS, BOT_TRADE_OUTCOMES
from bot.live_trader.constants_live_trader import LT_AUDIT_ACTION
from tests.test_bot_first_pullback import NOW, SYM, leg, paper, tick, trade_rows, trigger  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]


def _working(row: dict, *, qty: float, filled: float, avg: float | None) -> dict:
    return {**row, "status": "Submitted", "qty": qty, "filled_qty": filled, "remaining_qty": qty - filled,
            "avg_fill_price": avg}


# -- the marks ---------------------------------------------------------------------------------------
def test_each_growth_of_the_filled_shares_is_said_once():
    row = {"order_id": 7, "qty": 100.0, "filled_qty": 40.0, "remaining_qty": 60.0, "avg_fill_price": 25.1,
           "status": "Submitted", "entered_ts": 1.0}
    first = fill_progress.partial(row, phase="entry", leg="entry", order_id=7)
    assert first == {"phase": "entry", "leg": "entry", "order_id": 7, "qty": 100.0, "filled_qty": 40.0,
                     "remaining_qty": 60.0, "avg_fill_price": 25.1, "status": "Submitted"}
    assert fill_progress.partial(row, phase="entry", leg="entry", order_id=7) is None
    assert fill_progress.partial({**row, "filled_qty": 70.0, "remaining_qty": 30.0},
                                 phase="entry", leg="entry", order_id=7)["filled_qty"] == 70.0
    # The same id handed out again after a rewind is another order.
    again = fill_progress.partial({**row, "entered_ts": 2.0}, phase="entry", leg="entry", order_id=7)
    assert again is not None and again["filled_qty"] == 40.0
    fill_progress.forget(7)
    assert fill_progress.partial(row, phase="entry", leg="entry", order_id=7) is not None


def test_nothing_filled_says_nothing_and_remaining_falls_back_to_qty():
    assert fill_progress.partial({"qty": 10, "filled_qty": 0, "status": "Submitted"},
                                 phase="exit", leg="close", order_id=3) is None
    block = fill_progress.block({"qty": 10, "filled_qty": 4}, phase="exit", leg="close", order_id=3)
    assert block["remaining_qty"] == 6.0 and block["avg_fill_price"] is None
    assert fill_progress.words(block, "PLTR", "sold") == "sold 4 of 10 PLTR, 6 still working"


# -- Nova's own bot ----------------------------------------------------------------------------------
def test_a_resting_entry_filling_in_parts_writes_a_partial_line_each_time(paper, monkeypatch):
    runner_trigger = trigger(setup={"entry": 9.99, "trigger_price": 9.99})
    from bot.first_pullback import runner

    runner.submit(runner_trigger)
    trade = tick(paper)
    assert trade["state"] == "entering"
    real = fp_orders.order_row
    filled = {"n": 40.0}

    def fake(order_id):
        row = real(order_id)
        if row and int(order_id) == int(trade["entry_order_id"]) and row["status"] not in ("Filled", "Cancelled"):
            return _working(row, qty=100.0, filled=filled["n"], avg=9.99)
        return row

    monkeypatch.setattr(fp_orders, "order_row", fake)
    tick(paper, NOW + 0.5)
    tick(paper, NOW + 1.0)                      # the same 40: nothing more
    filled["n"] = 70.0
    tick(paper, NOW + 1.5)
    parts = trade_rows("partial")
    assert [p["fill"]["filled_qty"] for p in parts] == [40.0, 70.0]
    assert parts[0]["order_id"] == trade["entry_order_id"]
    assert parts[0]["fill"]["phase"] == "entry" and parts[0]["fill"]["leg"] == "entry"
    assert parts[0]["fill"]["remaining_qty"] == 60.0 and parts[0]["fill"]["avg_fill_price"] == 9.99
    assert parts[0]["reason"] == f"bought 40 of 100 {SYM} at 9.99, 60 still working (entry)"


def test_a_resting_target_filling_in_part_is_an_exit_partial_and_the_entry_fill_carries_its_block(paper,
                                                                                                    monkeypatch):
    from bot.first_pullback import runner

    runner.submit(trigger())
    trade = tick(paper)                         # marketable: filled in the send
    [filled] = trade_rows("filled")
    assert filled["fill"]["phase"] == "entry" and filled["fill"]["filled_qty"] == 1.0
    assert filled["fill"]["remaining_qty"] == 0.0 and filled["fill"]["avg_fill_price"] == 10.02
    real = fp_orders.order_row

    def fake(order_id):
        row = real(order_id)
        if row and int(order_id) == int(trade["target_order_id"]):
            return _working(row, qty=1.0, filled=0.4, avg=10.30)
        return row

    monkeypatch.setattr(fp_orders, "order_row", fake)
    tick(paper, NOW + 0.5)
    [part] = trade_rows("partial")
    assert part["fill"]["phase"] == "exit" and part["fill"]["leg"] == "target1"
    assert part["order_id"] == trade["target_order_id"]
    assert part["reason"] == f"sold 0.4 of 1 {SYM} at 10.3, 0.6 still working (target1)"


def test_a_target_that_fills_whole_puts_its_fill_on_the_closed_line(paper):
    from bot.first_pullback import runner

    runner.submit(trigger())
    trade = tick(paper)
    paper.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    tick(paper, NOW + 11)
    [closed] = trade_rows("closed")
    assert closed["fill"] == {"phase": "exit", "leg": "target1", "order_id": trade["target_order_id"], "qty": 1.0,
                              "filled_qty": 1.0, "remaining_qty": 0.0, "avg_fill_price": 10.30, "status": "Filled"}
    assert trade_rows("partial") == []


def test_shares_sold_outside_close_with_no_fill_block(paper):
    from bot.first_pullback import runner

    runner.submit(trigger())
    trade = tick(paper)
    paper.broker.cancel(trade["target_order_id"])
    paper.broker.place(SYM, "SELL", 1, "MKT")
    tick(paper, NOW + 2)
    tick(paper, NOW + 3)
    [closed] = trade_rows("closed")
    assert closed["inputs"]["exit_reason"] == "outside"
    assert "fill" not in closed


# -- the Live Trader bot -----------------------------------------------------------------------------
def _lt_pos(**over) -> dict:
    pos = {"id": "p1", "host": "SHAWN", "row_id": "r1", "symbol": "TSLA", "side": "long", "state": "open",
           "order": {"id": 41, "step": "open", "qty": 10.0, "limit": 250.0, "sent_ts": 100.0, "change": {}},
           "close": None}
    pos.update(over)
    return pos


def _lt_lines(outcome: str) -> list[dict]:
    return [r for r in list_entries(limit=50) if r["action"] == LT_AUDIT_ACTION and r["outcome"] == outcome]


def test_a_live_trader_step_filling_in_parts_writes_partials_then_its_filled_block(monkeypatch):
    rows = {"row": {"order_id": 41, "qty": 10.0, "filled_qty": 4.0, "remaining_qty": 6.0, "avg_fill_price": 250.0,
                    "status": "Submitted", "entered_ts": 99.0}}
    monkeypatch.setattr(lt_book, "get", lambda pos_id: _lt_pos())
    monkeypatch.setattr(lt_book, "step_done", lambda *a, **k: None)
    monkeypatch.setattr(lt_orders, "order_row", lambda oid: rows["row"])
    monkeypatch.setattr(lt_act, "market_now", lambda symbol: None)
    assert lt_act.follow_step("p1", 101.0) is None
    lt_act.follow_step("p1", 102.0)
    [part] = _lt_lines("partial")
    assert part["fill"] == {"phase": "entry", "leg": "open", "order_id": 41, "qty": 10.0, "filled_qty": 4.0,
                            "remaining_qty": 6.0, "avg_fill_price": 250.0, "status": "Submitted"}
    assert part["reason"] == "bought 4 of 10 TSLA at 250, 6 still working" and "fill" not in part["inputs"]
    rows["row"] = {**rows["row"], "status": "Filled", "filled_qty": 10.0, "remaining_qty": 0.0}
    lt_act.follow_step("p1", 103.0)
    [done] = _lt_lines("filled")
    assert done["fill"]["filled_qty"] == 10.0 and done["fill"]["remaining_qty"] == 0.0


def test_a_live_trader_close_filling_in_part_is_an_exit_partial(monkeypatch):
    close_ = {"order_id": 52, "qty": 10.0, "kind": "close", "sent_ts": 100.0}
    monkeypatch.setattr(lt_book, "get", lambda pos_id: _lt_pos(state="closing", order=None, close=close_))
    monkeypatch.setattr(lt_orders, "order_row", lambda oid: {"order_id": 52, "qty": 10.0, "filled_qty": 3.0,
                                                             "avg_fill_price": 251.0, "status": "Submitted"})
    lt_act.follow_close("p1", 101.0)
    [part] = _lt_lines("partial")
    assert part["fill"]["phase"] == "exit" and part["fill"]["leg"] == "close" and part["order_id"] == 52
    assert part["fill"]["remaining_qty"] == 7.0
    assert part["reason"] == "sold 3 of 10 TSLA at 251, 7 still working"


# -- fixed names -------------------------------------------------------------------------------------
def test_every_outcome_the_bots_write_is_a_fixed_name():
    assert LT_AUDIT_ACTION in BOT_TRADE_AUDIT_ACTIONS
    pattern = re.compile(r'outcome="([a-z_]+)"|\baudit\("([a-z_]+)"|\bnote\([^)]*outcome="([a-z_]+)"')
    seen: set[str] = set()
    for folder in ("bot/first_pullback", "bot/live_trader"):
        for path in (BACKEND / folder).glob("*.py"):
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                seen.add(next(g for g in match.groups() if g))
    assert seen and seen <= BOT_TRADE_OUTCOMES, sorted(seen - BOT_TRADE_OUTCOMES)


def test_a_trade_line_with_another_name_is_logged_and_still_written(caplog):
    with caplog.at_level(logging.ERROR, logger="bot.audit"):
        entry = record(action="bot_trade", outcome="half_filled", inputs={"symbol": "X"})
    assert entry["outcome"] == "half_filled" and list_entries(limit=1)[-1]["outcome"] == "half_filled"
    assert "outside BOT_TRADE_OUTCOMES" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="bot.audit"):
        record(action="level", outcome="1->2")
    assert caplog.text == ""
