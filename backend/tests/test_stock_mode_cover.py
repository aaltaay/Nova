"""Nova takes the cover of a stock you shorted (ADR 048 step 3: "Nova takes the exit" mirrored).

The operator shorts on Paper by hand and hands Nova the cover: a resting BUY stop over the price, lowered
as 1-minute candles close under round numbers, closed when it fills, taken back on request. The real
execution door and the real practice broker run against ``test_stock_mode``'s fake live market.
"""
from __future__ import annotations

import pytest

from bot.first_pullback import admit
from bot.first_pullback import orders as fp_orders
from stock_mode import exit_trade, orders, runner, store
from tests.bot_helpers import headers
from tests.test_stock_mode import NOW, SYM, api_key, client, mode_rows, paper, put, tick, trigger  # noqa: F401
from tests.test_stock_mode_exit import exit_rows, legs


def take(p, **body):
    data = {"stop": 10.20, "trail": True}
    data.update(body)
    return client.post(f"/api/stock-mode/{SYM}/take-exit", json=data, headers=headers(p.key))


@pytest.fixture
def shorting(paper, monkeypatch, short_market_open):
    """100 IMCC shorted by hand at the 9.98 bid; the last price 9.90."""
    paper.broker.place(SYM, "SELL", 100, "LMT", limit_price=9.98, short_entry=True)
    assert paper.broker.ledger.held_qty(SYM) == -100.0
    monkeypatch.setattr(orders, "last_price", lambda sym: 9.90)
    return paper


def test_nova_takes_the_cover_with_a_resting_buy_stop(shorting):
    r = take(shorting, stop=10.20)
    assert r.status_code == 200, r.text
    trade = r.json()["trade"]
    assert (trade["kind"], trade["side"], trade["state"], trade["exits"], trade["qty"]) == (
        "exit", "short", "holding", "nova", 100)
    assert trade["entry"] == pytest.approx(9.98)
    stop = legs(shorting)[trade["stop_order_id"]]
    assert (stop["side"], stop["order_type"], stop["stop_price"], stop["qty"]) == ("BUY", "STP", 10.20, 100.0)
    assert (stop["order_origin"], stop["effect"]) == ("nova_exit", "closes")
    assert "Nova took the cover: buy stop 10.20" in r.json()["last_event"]["text"] and exit_rows("sent")


def test_a_buy_stop_that_would_cover_at_once_is_refused(shorting):
    r = take(shorting, stop=9.85)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_INVALID"
    assert "would cover at once" in r.json()["detail"]["error"] and shorting.broker.ledger.working_orders() == []


def test_the_buy_stop_that_fills_closes_the_trade_with_the_shorts_loss(shorting):
    take(shorting, stop=10.20)
    shorting.broker.try_fill_working(SYM, [(NOW + 5, 10.21)])
    done = tick(shorting, NOW + 6)
    assert (done["state"], done["exit_reason"], done["exit_price"]) == ("closed", "stop", 10.21)
    assert shorting.broker.ledger.held_qty(SYM) == 0.0
    assert "Nova's buy stop 10.20 filled" in store.event(SYM)["text"] and "-$23.00" in store.event(SYM)["text"]


def test_covering_outside_nova_closes_it(shorting):
    trade = take(shorting, stop=10.20).json()["trade"]
    shorting.broker.cancel(trade["stop_order_id"])
    shorting.broker.place(SYM, "BUY", 100, "MKT")
    done = tick(shorting, NOW + 6)
    assert done["state"] == "closed" and done["exit_reason"] == "outside"


def test_trail_lowers_the_buy_stop_once_a_candle_closes_under_a_round_number(shorting, monkeypatch):
    trade = take(shorting, stop=10.20).json()["trade"]
    start = int(trade["sent_at"] // 60) * 60
    # 15 closes over $9.50, then a candle that closes 9.44 under it
    bars = [{"t": start - 60 * (16 - i), "o": 9.9, "h": 9.95, "l": 9.85, "c": 9.9, "v": 100} for i in range(16)]
    bars.append({"t": start, "o": 9.8, "h": 9.82, "l": 9.40, "c": 9.44, "v": 500})
    monkeypatch.setattr(exit_trade, "_closed_bars", lambda sym, now: bars)
    monkeypatch.setattr(orders, "last_price", lambda sym: 9.42)
    done = tick(shorting, start + 61)
    assert done["stop"] == 9.55 and done["raised"][-1] == {"at": start + 61, "from": 10.20, "to": 9.55, "round": 9.5}
    assert legs(shorting)[done["stop_order_id"]]["stop_price"] == 9.55
    assert "lowered the buy stop 10.20 -> 9.55" in store.event(SYM)["text"] and exit_rows("lowered")
    again = tick(shorting, start + 65)                          # once per minute, and never up
    assert again["stop"] == 9.55 and len(again["raised"]) == 1


# -- Nova never enters against a position you hold (ADR 048) -------------------------------------
def test_auto_entry_buys_nothing_while_you_hold_the_stock_short(shorting):
    put(shorting, "nova", "you")
    runner.submit(trigger())
    tick(shorting)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == "BOT_SKIP_HELD_OTHER_SIDE"
    assert "you hold IMCC short: Nova enters nothing on IMCC while you do" in skip["reason"]
    assert shorting.broker.ledger.held_qty(SYM) == -100.0 and shorting.broker.ledger.working_orders() == []


def test_the_held_side_guard_refuses_an_unreadable_position(monkeypatch):
    monkeypatch.setattr(fp_orders, "short_held_qty", lambda sym: 0.0)
    monkeypatch.setattr(fp_orders, "held_qty", lambda sym: 0.0)
    assert admit.against_held("IMCC") is None and admit.against_held("IMCC", "short") is None
    monkeypatch.setattr(fp_orders, "held_qty", lambda sym: 50.0)
    code, why = admit.against_held("IMCC", "short")
    assert code == "BOT_SKIP_HELD_OTHER_SIDE" and why == "you hold IMCC long: Nova enters nothing on IMCC while you do"

    def unreadable(sym):
        raise fp_orders.ReadError("position unreadable: Gateway down")

    monkeypatch.setattr(fp_orders, "short_held_qty", unreadable)
    code, why = admit.against_held("IMCC")
    assert code == "BOT_SKIP_HELD_OTHER_SIDE" and "cannot read your IMCC position" in why


# -- Who trades is Entry · Exit (ADR 048) -----------------------------------------------------------
def test_the_switch_takes_entry_and_exit_and_says_both_names(paper):
    r = client.put(f"/api/stock-mode/{SYM}", json={"entry": "nova", "exit": "you"}, headers=headers(paper.key))
    assert r.status_code == 200, r.text
    view = r.json()
    assert (view["mode"], view["entry"], view["exit"], view["buy"], view["sell"]) == (
        "auto_entry", "nova", "you", "nova", "you")
    assert view["locks"] == {"entry": None, "exit": None, "buy": None, "sell": None,
                             "modes": {"bot": None, "auto_entry": None, "approve": None}}
    assert client.put(f"/api/stock-mode/{SYM}", json={"entry": "nova"}, headers=headers(paper.key)).status_code == 422


def test_a_nova_mode_names_the_short_you_hold(shorting):
    put(shorting, "nova", "you")
    notes = {n["id"]: n["text"] for n in client.get(f"/api/stock-mode/{SYM}").json()["notes"]}
    assert notes["held_other_side"] == "You hold IMCC short: Nova enters nothing on IMCC while you do."


def test_exit_to_nova_on_a_held_short_points_at_the_cover(shorting):
    r = put(shorting, "you", "nova")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_HELD"
    assert "Nova takes the cover" in r.json()["detail"]["error"]
