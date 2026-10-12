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
    """The targets rest beside the stop as one exit pair, committed once (#681); any other SELL of the same
    shares is still the door's to refuse."""
    from execution.models import ExecutionCommand
    from execution.service import execute

    trade = take(holding, stop=9.80, target=10.30, target2=10.60).json()["trade"]
    assert len(holding.broker.ledger.working_orders()) == 3 and holding.broker.ledger.held_qty(SYM) == 100.0
    second = asyncio.run(execute(ExecutionCommand(
        operation="place", idempotency_key="second-sell", source="manual", symbol=SYM, side="SELL", qty=10,
        order_type="LMT", limit_price=10.50, skip_risk=True)))
    assert second.ok is False and second.reason_code == "OVERSELL"
    assert legs(holding)[trade["stop_order_id"]]["qty"] == 100.0       # one stop for every share


def test_nova_rests_two_targets_beside_its_stop(holding):
    r = take(holding, stop=9.80, target=10.30, target2=10.60)
    assert r.status_code == 200, r.text
    trade = r.json()["trade"]
    assert (trade["target"], trade["target2"]) == (10.30, 10.60)
    rows = legs(holding)
    stop, t1, t2 = (rows[trade[k]] for k in ("stop_order_id", "target_order_id", "target2_order_id"))
    assert (stop["order_type"], stop["stop_price"], stop["qty"]) == ("STP", 9.80, 100.0)
    assert (t1["order_type"], t1["limit_price"], t1["qty"]) == ("LMT", 10.30, 50.0)
    assert (t2["order_type"], t2["limit_price"], t2["qty"]) == ("LMT", 10.60, 50.0)
    assert {stop["order_origin"], t1["order_origin"], t2["order_origin"]} == {"nova_exit"}
    assert "target 1 10.30 for 50, target 2 10.60 for 50" in store.event(SYM)["text"]


def test_target_one_sells_half_and_the_stop_stays_where_it_is(holding):
    trade = take(holding, stop=9.80, target=10.30, target2=10.60).json()["trade"]
    holding.broker.try_fill_working(SYM, [(NOW + 5, 10.35)])
    done = tick(holding, NOW + 6)
    assert done["state"] == "holding" and [(h["leg"], h["qty"]) for h in done["halves"]] == [("target1", 50.0)]
    stop = legs(holding)[trade["stop_order_id"]]
    assert (stop["status"], stop["qty"], stop["stop_price"]) == ("Submitted", 50.0, 9.80)
    assert done["stop"] == 9.80 and "stays for the other 50" in store.event(SYM)["text"] and exit_rows("half")
    holding.broker.try_fill_working(SYM, [(NOW + 9, 9.79)])
    done = tick(holding, NOW + 10)
    assert (done["state"], done["exit_reason"]) == ("closed", "stop")
    assert done["exit_price"] == pytest.approx((10.30 + 9.79) / 2)
    assert "+$2.50" in store.event(SYM)["text"]                            # 50 x 0.28 - 50 x 0.23, both halves
    assert legs(holding)[trade["target2_order_id"]]["status"] == "Cancelled"
    assert holding.broker.ledger.held_qty(SYM) == 0.0


def test_one_target_sells_every_share_and_closes_it(holding):
    trade = take(holding, stop=9.80, target=10.30).json()["trade"]
    assert trade["target2"] is None and trade["target2_order_id"] is None
    assert legs(holding)[trade["target_order_id"]]["qty"] == 100.0
    holding.broker.try_fill_working(SYM, [(NOW + 5, 10.35)])
    done = tick(holding, NOW + 6)
    assert (done["state"], done["exit_reason"], done["exit_price"]) == ("closed", "target", 10.30)
    assert legs(holding)[trade["stop_order_id"]]["status"] == "Cancelled" and "+$28.00" in store.event(SYM)["text"]


def test_a_trail_raise_moves_the_stop_and_keeps_the_targets(holding, monkeypatch):
    trade = take(holding, stop=9.80, target=10.70, target2=11.00).json()["trade"]
    start = int(trade["sent_at"] // 60) * 60
    bars = [{"t": start - 60 * (16 - i), "o": 10.0, "h": 10.1, "l": 9.95, "c": 10.0, "v": 100} for i in range(16)]
    bars.append({"t": start, "o": 10.1, "h": 10.6, "l": 10.05, "c": 10.56, "v": 500})
    monkeypatch.setattr(exit_trade, "_closed_bars", lambda sym, now: bars)
    monkeypatch.setattr(orders, "last_price", lambda sym: 10.58)
    holding.ref.last, holding.ref.bid, holding.ref.ask = 10.58, 10.57, 10.59   # the venue's market moved up too
    done = tick(holding, start + 61)
    assert done["stop"] == 10.45
    rows = legs(holding)
    assert rows[trade["stop_order_id"]]["status"] == "Submitted"
    assert rows[trade["stop_order_id"]]["stop_price"] == 10.45
    assert rows[trade["target_order_id"]]["status"] == rows[trade["target2_order_id"]]["status"] == "Submitted"


@pytest.mark.parametrize("body, field", [
    ({"target": 9.99}, "target"),                     # at or under the last price: it would sell at once
    ({"target": 9.70}, "target"),                     # under the stop
    ({"target": 10.30, "target2": 10.20}, "target2"),  # target 2 not beyond target 1
    ({"target2": 10.60}, "target"),                   # target 2 alone
])
def test_a_target_that_does_not_hang_together_is_refused(holding, body, field):
    r = take(holding, stop=9.80, **body)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_INVALID"
    assert r.json()["detail"]["field"] == field and holding.broker.ledger.working_orders() == []


def test_take_it_back_cancels_the_stop_and_both_targets(holding):
    trade = take(holding, stop=9.80, target=10.30, target2=10.60).json()["trade"]
    body = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(holding.key)).json()
    assert body["trade"]["state"] == "handed"
    rows = legs(holding)
    assert {rows[trade[k]]["status"] for k in ("stop_order_id", "target_order_id", "target2_order_id")} == {"Cancelled"}
    assert holding.broker.ledger.held_qty(SYM) == 100.0


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
