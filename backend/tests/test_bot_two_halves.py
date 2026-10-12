"""Nova's bot sells in two halves (#681, #845): half at target 1, the rest at target 2, the stop left where it is.

The entry is one practice bracket with a second target: a BUY limit, a SELL limit at target 1 for the
first half, a SELL limit at target 2 for the rest and a SELL stop for every share, the stop shrinking as
the targets fill. The trade books each sale (``halves``) and counts every share in its exit price and R.
A setup row with no ``target2`` sells every share at target 1, as before. The real execution door and the
real Paper broker run against ``test_bot_first_pullback``'s fake live market.
"""
from __future__ import annotations

import pytest

from bot.autonomy import apply_patch
from bot.first_pullback import orders as fp_orders
from bot.first_pullback import runner
from bot.persist import load_session
from constants_bot import BOT_FP_TIME_STOP_MIN
from tests.test_bot_first_pullback import NOW, SYM, leg, paper, tick, trade_rows, trigger  # noqa: F401 (fixtures)


@pytest.fixture
def four(paper):
    """The sleeve sizes four shares: $20 risk / $0.13 a share, capped at 4, the $50 budget room for them."""
    apply_patch({"caps": {"max_shares": 4, "bp_budget_usd": 50.0}}, desk=True)
    return paper


def halves_trigger(**setup) -> dict:
    return trigger(setup={"target2": 10.60, "target1_fraction": 0.5, **setup})


def test_the_bracket_rests_two_targets_and_a_stop_for_every_share(four):
    runner.submit(halves_trigger())
    trade = tick(four)
    assert trade["state"] == "open" and trade["qty"] == 4 and trade["entry_qty"] == 4
    t1, t2, stop = (leg(four, trade[k]) for k in ("target_order_id", "target2_order_id", "stop_order_id"))
    assert (t1["limit_price"], t1["qty"]) == (10.30, 2) and (t2["limit_price"], t2["qty"]) == (10.60, 2)
    assert (stop["stop_price"], stop["qty"], stop["status"]) == (9.89, 4, "Submitted")
    assert {t1["oca_group"], t2["oca_group"], stop["oca_group"]} == {t1["oca_group"]}
    [entry] = [r for r in trade_rows() if r["outcome"] == "filled"]
    assert "target 10.3 for 2 and 10.6 for 2" in entry["reason"]


def test_target_one_sells_half_and_the_stop_stays_for_the_rest(four):
    runner.submit(halves_trigger())
    tick(four)
    four.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    trade = tick(four, NOW + 11)
    assert trade["state"] == "open" and trade["qty"] == 2
    assert trade["halves"] == [{"leg": "target1", "qty": 2.0, "price": 10.30, "ts": NOW + 11,
                                "order_id": trade["target_order_id"]}]
    stop = leg(four, trade["stop_order_id"])
    assert (stop["qty"], stop["stop_price"], stop["status"]) == (2, 9.89, "Submitted")   # never moved to the entry
    assert trade["stop"] == 9.89 and leg(four, trade["target2_order_id"])["status"] == "Submitted"
    assert load_session()["bot_qty"] == {SYM: 2.0} and four.broker.ledger.held_qty(SYM) == 2
    [half] = trade_rows("half")
    assert "sold 2 at target 1 10.3; the stop 9.89 stays for the other 2" in half["reason"]

    four.broker.try_fill_working(SYM, [(NOW + 20, 9.85)])                 # the stop sells the rest
    trade = tick(four, NOW + 21)
    assert (trade["state"], trade["exit_reason"]) == ("closed", "stop")
    assert [(h["leg"], h["qty"], h["price"]) for h in trade["halves"]] == [("target1", 2.0, 10.30),
                                                                            ("stop", 2.0, 9.85)]
    assert trade["exit_price"] == pytest.approx(10.075)
    assert trade["r"] == pytest.approx(round((2 * 0.28 - 2 * 0.17) / (4 * 0.14), 3))
    assert four.broker.ledger.held_qty(SYM) == 0 and load_session()["bot_qty"] == {}
    assert leg(four, trade["target2_order_id"])["status"] == "Cancelled"
    [closed] = trade_rows("closed")
    assert "target 1 10.3 x 2, stop 9.85 x 2" in closed["reason"] and closed["inputs"]["halves"] == trade["halves"]
    # The day's P&L is the ledger's: both halves, every fee.
    gross = 2 * (10.30 - 10.02) + 2 * (9.85 - 10.02)
    assert four.broker.ledger.realized_today() == pytest.approx(gross - four.broker.ledger.commissions_today())


def test_both_targets_close_the_trade_at_target_two(four):
    runner.submit(halves_trigger())
    tick(four)
    four.broker.try_fill_working(SYM, [(NOW + 10, 10.35), (NOW + 12, 10.65)])
    trade = tick(four, NOW + 13)
    assert (trade["state"], trade["exit_reason"]) == ("closed", "target")
    assert [(h["leg"], h["price"]) for h in trade["halves"]] == [("target1", 10.30), ("target2", 10.60)]
    assert trade["exit_price"] == pytest.approx(10.45) and trade["r"] == pytest.approx(round(4.3 / 1.4, 3))
    assert leg(four, trade["stop_order_id"])["status"] == "Cancelled"
    assert "target 2 10.6 filled" in trade_rows("closed")[0]["reason"]
    assert four.broker.ledger.working_orders() == [] and load_session()["bot_qty"] == {}


def test_the_time_stop_after_a_half_sells_what_is_left(four):
    runner.submit(halves_trigger())
    tick(four)
    four.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    trade = tick(four, NOW + 11)
    rest = trade["target2_order_id"], trade["stop_order_id"]
    trade = tick(four, NOW + BOT_FP_TIME_STOP_MIN * 60 + 1)
    assert trade["state"] == "exiting" and trade["exit_why"] == "time"
    assert {leg(four, oid)["status"] for oid in rest} == {"Cancelled"}
    trade = tick(four, NOW + BOT_FP_TIME_STOP_MIN * 60 + 2)
    assert (trade["state"], trade["exit_reason"]) == ("closed", "time")
    assert [(h["leg"], h["qty"]) for h in trade["halves"]] == [("target1", 2.0), ("time", 2.0)]
    assert four.broker.ledger.held_qty(SYM) == 0.0


def test_an_odd_count_gives_the_first_half_the_smaller_part(four):
    apply_patch({"caps": {"max_shares": 3}}, desk=True)
    runner.submit(halves_trigger())
    trade = tick(four)
    assert (leg(four, trade["target_order_id"])["qty"], leg(four, trade["target2_order_id"])["qty"]) == (1, 2)


@pytest.mark.parametrize("setup", [{}, {"target2": None, "target1_fraction": None}])
def test_no_second_target_sells_every_share_at_target_one(four, setup):
    runner.submit(trigger(setup=setup))
    trade = tick(four)
    assert trade["target2"] is None and trade["target2_order_id"] is None
    assert leg(four, trade["target_order_id"])["qty"] == 4 and leg(four, trade["stop_order_id"])["qty"] == 4
    four.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    trade = tick(four, NOW + 11)
    assert (trade["state"], trade["exit_reason"], trade["exit_price"]) == ("closed", "target", 10.30)
    assert leg(four, trade["stop_order_id"])["status"] == "Cancelled" and trade_rows("half") == []


def test_one_share_sells_whole_at_target_one(paper):
    runner.submit(halves_trigger())
    trade = tick(paper)
    assert trade["qty"] == 1 and trade["target2_order_id"] is None
    assert leg(paper, trade["target_order_id"])["qty"] == 1


def test_the_halves_go_out_in_the_one_bracket_and_a_repeat_replays_every_legs_id(four, monkeypatch):
    """The legs are one command under the entry's key (committed and placed together); a repeat of that key
    replays the receipt -- every leg's own order id, the second target's included -- and places nothing."""
    import asyncio

    seen = []
    real = fp_orders.execute

    async def spy(cmd, **kw):
        seen.append(cmd)
        return await real(cmd, **kw)

    monkeypatch.setattr(fp_orders, "execute", spy)
    runner.submit(halves_trigger())
    trade = tick(four)
    [bracket] = [c for c in seen if c.operation == "bracket"]
    assert (bracket.target_price, bracket.target2_price, bracket.target1_qty) == (10.30, 10.60, 2.0)
    assert bracket.idempotency_key.endswith(":entry")
    ids = {trade["entry_order_id"], trade["target_order_id"], trade["target2_order_id"], trade["stop_order_id"]}
    assert len(ids) == 4
    working = len(four.broker.ledger.working_orders())
    again = asyncio.run(real(bracket, wait_ack=False))
    assert again.duplicate is True and again.target2_order_id == trade["target2_order_id"]
    assert len(four.broker.ledger.working_orders()) == working


def test_a_take_over_after_a_half_hands_the_rest(four):
    from bot.first_pullback.handover import hand_over
    import asyncio

    runner.submit(halves_trigger())
    tick(four)
    four.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    tick(four, NOW + 11)
    trade = asyncio.run(hand_over(SYM, now=NOW + 12))
    assert trade["state"] == "handed" and trade["target2_order_id"] is None and trade["stop_order_id"] is None
    assert [(h["leg"], h["qty"]) for h in trade["halves"]] == [("target1", 2.0), ("handed", 2.0)]
    assert four.broker.ledger.working_orders() == [] and four.broker.ledger.held_qty(SYM) == 2
