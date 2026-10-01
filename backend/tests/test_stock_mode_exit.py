"""Nova takes the exit of a stock you bought (ADR 037 amendment 2026-10-01).

The operator buys on Paper by hand and hands Nova the sell: a resting SELL stop (and target), raised as
1-minute candles close over round numbers, closed when a leg fills, taken back on request. The real
execution door and the real practice broker run against ``test_stock_mode``'s fake live market.
"""
from __future__ import annotations

import asyncio

import pytest

from bot.audit import list_entries
from stock_mode import exit_trade, orders, runner, store
from tests.bot_helpers import headers
from tests.test_stock_mode import NOW, SYM, api_key, client, paper, put, tick  # noqa: F401 (fixtures)


def take(p, **body):
    data = {"stop": 9.80, "trail": True}
    data.update(body)
    return client.post(f"/api/stock-mode/{SYM}/take-exit", json=data, headers=headers(p.key))


def legs(p) -> dict[int, dict]:
    ledger = p.broker.ledger
    return {int(r["order_id"]): r for r in [*ledger.working_orders(), *ledger.closed_orders()]}


def exit_rows(outcome: str) -> list[dict]:
    return [r for r in list_entries(limit=100) if r["action"] == "stock_mode" and r["outcome"] == outcome]


@pytest.fixture
def holding(paper, monkeypatch):
    """100 IMCC bought by hand at the 10.02 ask; the last price 10.00."""
    paper.broker.place(SYM, "BUY", 100, "MKT")
    monkeypatch.setattr(orders, "last_price", lambda sym: 10.00)
    return paper


def test_nova_takes_the_exit_with_a_resting_stop(holding):
    r = take(holding, stop=9.80)
    assert r.status_code == 200, r.text
    view = r.json()
    trade = view["trade"]
    assert (trade["kind"], trade["state"], trade["exits"], trade["qty"]) == ("exit", "holding", "nova", 100)
    assert trade["entry"] == pytest.approx(10.02) and trade["trail"] is True and trade["raised"] == []
    assert trade["target"] is None and trade["target_order_id"] is None
    assert view["sell"] == "nova" and view["mode"] == "signal"     # the mode stays yours; Nova holds the sell
    stop = legs(holding)[trade["stop_order_id"]]
    assert (stop["side"], stop["order_type"], stop["stop_price"], stop["qty"]) == ("SELL", "STP", 9.80, 100.0)
    assert stop["order_origin"] == "nova_exit"
    assert "Nova took the exit" in view["last_event"]["text"] and exit_rows("sent")


def test_a_second_sell_of_the_same_shares_is_the_doors_to_refuse(holding):
    """Why no target rests beside the stop: the door lets one order sell the same shares."""
    take(holding, stop=9.80)
    second = holding.broker.ledger.held_qty(SYM)
    assert second == 100.0 and len(holding.broker.ledger.working_orders()) == 1


def test_on_live_it_is_locked_and_says_why(holding):
    from sim.mode import set_venue

    set_venue("live")
    r = take(holding)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_LIVE"
    assert "never moves a Live order" in r.json()["detail"]["error"]


def test_nothing_held_is_said(paper, monkeypatch):
    monkeypatch.setattr(orders, "last_price", lambda sym: 10.00)
    r = take(paper)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_NOTHING_HELD"


def test_a_stop_that_would_sell_at_once_is_refused(holding):
    r = take(holding, stop=10.00)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_INVALID"
    assert r.json()["detail"]["field"] == "stop" and holding.broker.ledger.working_orders() == []


def test_a_second_take_is_refused_while_nova_holds_it(holding):
    take(holding)
    r = take(holding)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_HELD"


def test_the_stop_that_fills_closes_the_trade(holding):
    take(holding, stop=9.80)
    holding.broker.try_fill_working(SYM, [(NOW + 5, 9.79)])
    done = tick(holding, NOW + 6)
    # A practice stop fills at the print that crossed it (9.79), not at its own price.
    assert (done["state"], done["exit_reason"], done["exit_price"]) == ("closed", "stop", 9.79)
    assert holding.broker.ledger.held_qty(SYM) == 0.0
    assert "-$23.00" in store.event(SYM)["text"]


def test_selling_outside_nova_closes_it_and_cancels_its_orders(holding):
    trade = take(holding, stop=9.80).json()["trade"]
    holding.broker.cancel(trade["stop_order_id"])                 # (a sale must free the shares first)
    holding.broker.place(SYM, "SELL", 100, "MKT")
    done = tick(holding, NOW + 6)
    assert done["state"] == "closed" and done["exit_reason"] == "outside"


def test_a_stop_cancelled_outside_nova_hands_the_exit_back(holding):
    trade = take(holding, stop=9.80).json()["trade"]
    holding.broker.cancel(trade["stop_order_id"])
    done = tick(holding, NOW + 6)
    assert (done["state"], done["exits"]) == ("handed", "you") and "outside Nova" in done["note"]


def test_take_it_back_cancels_the_stop_and_keeps_the_shares(holding):
    trade = take(holding, stop=9.80).json()["trade"]
    body = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(holding.key)).json()
    assert body["trade"]["state"] == "handed" and body["sell"] == "you"
    assert legs(holding)[trade["stop_order_id"]]["status"] == "Cancelled"
    assert holding.broker.ledger.held_qty(SYM) == 100.0


def test_sell_you_on_the_switch_takes_it_back(holding):
    take(holding)
    r = put(holding, "you", "you")
    assert r.status_code == 200 and r.json()["trade"]["state"] == "handed" and r.json()["sell"] == "you"


def test_sell_nova_on_the_switch_still_refuses_and_points_at_the_exit(holding):
    r = put(holding, "you", "nova")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_HELD"
    assert "Nova takes the exit" in r.json()["detail"]["error"]


def _minute(m: int) -> float:
    return float(int(NOW // 60) * 60 + m * 60)


def test_trail_raises_the_stop_once_a_candle_closes_over_a_round_number(holding, monkeypatch):
    trade = take(holding, stop=9.80).json()["trade"]
    t0 = trade["sent_at"]
    start = int(t0 // 60) * 60
    # 15 closes under $10.50, then a candle that closes 10.56 over it
    bars = [{"t": start - 60 * (16 - i), "o": 10.0, "h": 10.1, "l": 9.95, "c": 10.0, "v": 100} for i in range(16)]
    bars.append({"t": start, "o": 10.1, "h": 10.6, "l": 10.05, "c": 10.56, "v": 500})
    monkeypatch.setattr(exit_trade, "_closed_bars", lambda sym, now: bars)
    monkeypatch.setattr(orders, "last_price", lambda sym: 10.58)
    done = tick(holding, start + 61)
    assert done["stop"] == 10.45 and done["raised"][-1]["round"] == 10.5 and done["raised"][-1]["from"] == 9.80
    assert legs(holding)[done["stop_order_id"]]["stop_price"] == 10.45
    assert "raised the stop" in store.event(SYM)["text"] and exit_rows("raised")
    again = tick(holding, start + 65)                               # once per minute, and never down
    assert again["stop"] == 10.45 and len(again["raised"]) == 1


def test_trail_off_never_moves_the_stop(holding, monkeypatch):
    trade = take(holding, stop=9.80, trail=False).json()["trade"]
    start = int(trade["sent_at"] // 60) * 60
    bars = [{"t": start - 60 * (16 - i), "o": 10.0, "h": 10.1, "l": 9.95, "c": 10.0, "v": 100} for i in range(16)]
    bars.append({"t": start, "o": 10.1, "h": 10.6, "l": 10.05, "c": 10.56, "v": 500})
    monkeypatch.setattr(exit_trade, "_closed_bars", lambda sym, now: bars)
    monkeypatch.setattr(orders, "last_price", lambda sym: 10.58)
    assert tick(holding, start + 61)["stop"] == 9.80


def test_the_runner_manages_it_only_on_its_venue(holding):
    from sim.mode import set_venue

    take(holding)
    set_venue("sim")
    asyncio.run(runner.tick())
    assert store.trade("paper", SYM)["state"] == "holding"
