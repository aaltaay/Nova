"""Approve sells in two halves (#845, #681): the approved plan's bracket carries its target 2.

The operator approves the plan with its two targets; at the trigger Nova sends one bracket -- the entry, target 1
for the first half, target 2 for the rest and a stop for every share -- by the one split rule the bot and Nova's
exit use (``exit_targets.apply``, ``halves.split``). A first half that fills is booked, the stop shrinks at the
broker and never moves, and the trade closes when every share is sold. A plan without a target 2 sends one target,
as before. The real execution door and the real practice broker run on Paper against ``test_stock_mode``'s fake
live market; the short mirror is in ``test_bot_shorts``, the Sim rewind in ``test_stock_mode_sim_replay``.
"""
from __future__ import annotations

import pytest

from stock_mode import orders as sm_orders
from stock_mode import runner, store
from tests.bot_helpers import headers
from tests.test_stock_mode import (  # noqa: F401 -- fixtures
    NOW,
    SYM,
    _legs,
    api_key,
    approve_body,
    client,
    lane,
    mode_rows,
    paper,
    put,
    tick,
    trigger,
)

HALVES = {"target2": 10.50, "target1_fraction": 0.5}


def halves_lane(**over) -> dict:
    return lane(setup={**HALVES, **over.pop("setup", {})}, **over)


def approve(p, **over):
    return client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(**{**HALVES, **over}),
                       headers=headers(p.key))


@pytest.fixture
def approved(paper, monkeypatch):
    """IMCC in Approve, its plan approved with both targets: 153 shares, 76 at 10.28 and 77 at 10.50."""
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: halves_lane())
    put(paper, "you", "nova")
    r = approve(paper)
    assert r.status_code == 200, r.text
    return paper


def holding(p) -> dict:
    runner.submit(trigger())
    tick(p)                                                  # the bracket goes out: the entry takes the 10.02 ask
    trade = tick(p, NOW + 0.5)
    assert trade["state"] == "holding" and trade["fill_price"] == 10.02
    return trade


# -- the approval ------------------------------------------------------------------------------
def test_the_approval_carries_the_plans_target_2_and_its_share(approved):
    approval = store.approval(SYM)
    assert (approval["target"], approval["target2"], approval["target1_fraction"]) == (10.28, 10.50, 0.5)
    [row] = mode_rows("approved")
    assert "target 1 10.28, target 2 10.50 at the trigger" in row["reason"]
    assert client.get(f"/api/stock-mode/{SYM}").json()["approval"]["target2"] == 10.50


@pytest.mark.parametrize("lane_t2, body_t2, words", [
    (10.50, None, "10.02 / 9.89 / 10.28 / 10.50"),            # the lane has a target 2 the approval left out
    (None, 10.50, "10.02 / 9.89 / 10.28 now"),                # an approval's target 2 the lane does not have
    (10.60, 10.50, "10.02 / 9.89 / 10.28 / 10.60"),           # another target 2
])
def test_an_approval_binds_to_the_lanes_target_2_too(paper, monkeypatch, lane_t2, body_t2, words):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane(setup={"target2": lane_t2}))
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(target2=body_t2), headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_PLAN_CHANGED"
    assert words in r.json()["detail"]["error"] and store.approval(SYM) is None


def test_a_target_2_that_moves_after_the_approval_withdraws_it(approved, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: halves_lane(setup={"target2": 10.60}))
    tick(approved, NOW + 3)
    approval = client.get(f"/api/stock-mode/{SYM}").json()["approval"]
    assert approval["state"] == "withdrawn" and "re-armed at 10.02 / 9.89 / 10.28 / 10.60" in approval["reason"]


@pytest.mark.parametrize("over, field, words", [
    ({"target2": 10.28}, "target2", "target 2 10.28 must be over target 1 10.28"),
    ({"target2": 10.10}, "target2", "target 2 10.10 must be over target 1 10.28"),
    ({"target1_fraction": 0}, "target1_fraction", "over 0 and at most 1"),
    ({"target1_fraction": 1.5}, "target1_fraction", "over 0 and at most 1"),
])
def test_target_2_must_be_past_target_1_and_the_share_a_fraction(paper, monkeypatch, over, field, words):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: halves_lane())
    put(paper, "you", "nova")
    r = approve(paper, **over)
    detail = r.json()["detail"]
    assert r.status_code == 400 and (detail["reason"], detail["field"]) == ("STOCK_MODE_INVALID", field)
    assert words in detail["error"] and store.approval(SYM) is None


def test_a_short_plans_cover_2_must_be_under_cover_1(paper, monkeypatch):
    short = lane(setup_type="bear_flag", side="short",
                 setup={"trigger": 9.99, "entry": 9.98, "stop": 10.11, "target1": 9.72, "target2": 9.50})
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: short)
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", headers=headers(paper.key),
                    json=approve_body(entry=9.98, stop=10.11, target=9.72, target2=9.80))
    assert r.status_code == 400 and "cover 2 9.80 must be under cover 1 9.72" in r.json()["detail"]["error"]
    ok = client.post(f"/api/stock-mode/{SYM}/approve", headers=headers(paper.key),
                     json=approve_body(entry=9.98, stop=10.11, target=9.72, target2=9.50, target1_fraction=0.5))
    assert ok.status_code == 200, ok.text
    assert (store.approval(SYM)["side"], store.approval(SYM)["target2"]) == ("short", 9.50)


# -- the send ----------------------------------------------------------------------------------
@pytest.fixture
def commands(monkeypatch):
    """Every command the stock-mode orders send, passed on to the real door."""
    seen = []
    real = sm_orders.execute

    async def spy(cmd, **kw):
        seen.append(cmd)
        return await real(cmd, **kw)

    monkeypatch.setattr(sm_orders, "execute", spy)
    return seen


def test_the_bracket_sends_target_2_and_the_first_halfs_shares(approved, commands):
    trade = holding(approved)
    [bracket] = [c for c in commands if c.operation == "bracket"]
    assert (bracket.side, bracket.qty, bracket.target_price, bracket.target2_price, bracket.target1_qty) == (
        "BUY", 153.0, 10.28, 10.50, 76.0)                          # an odd count: the first half the smaller part
    assert (trade["target1_qty"], trade["target2_qty"], trade["target1_fraction"]) == (76, 77, 0.5)
    legs = _legs(approved)
    t1, t2, stop = (legs[trade[k]] for k in ("target_order_id", "target2_order_id", "stop_order_id"))
    assert (t1["leg_role"], t1["limit_price"], t1["qty"]) == ("target", 10.28, 76)
    assert (t2["leg_role"], t2["limit_price"], t2["qty"]) == ("target2", 10.50, 77)
    assert (stop["stop_price"], stop["qty"]) == (9.89, 153)
    assert {t1["oca_group"], t2["oca_group"], stop["oca_group"]} == {f"oca-{trade['entry_order_id']}"}
    [sent] = mode_rows("sent")
    assert "target 1 10.28 for 76, target 2 10.50 for 77, stop 9.89 (one bracket)" in sent["reason"]
    assert "both targets rest at the broker" in mode_rows("filled")[0]["reason"]


def test_a_plan_without_target_2_sends_one_target_as_before(paper, monkeypatch, commands):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    assert client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(),
                       headers=headers(paper.key)).status_code == 200
    trade = holding(paper)
    [bracket] = [c for c in commands if c.operation == "bracket"]
    assert (bracket.target_price, bracket.target2_price, bracket.target1_qty) == (10.28, None, None)
    assert trade["target2"] is None and trade["target2_order_id"] is None
    assert _legs(paper)[trade["target_order_id"]]["qty"] == 153


def test_one_share_sells_whole_at_target_1(approved, monkeypatch, commands):
    store.clear_approval(SYM)
    assert approve(approved, qty=1).status_code == 200
    trade = holding(approved)
    [bracket] = [c for c in commands if c.operation == "bracket"]
    assert (bracket.target2_price, bracket.target1_qty) == (None, None)
    assert trade["target2"] is None and _legs(approved)[trade["target_order_id"]]["qty"] == 1


# -- the halves --------------------------------------------------------------------------------
def test_target_1_sells_the_first_half_and_the_stop_stays_for_the_rest(approved):
    trade = holding(approved)
    approved.broker.try_fill_working(SYM, [(NOW + 2, 10.30)])          # through target 1, short of target 2
    trade = tick(approved, NOW + 2.5)
    assert trade["state"] == "holding" and trade["exits"] == "nova"
    assert trade["halves"] == [{"leg": "target1", "qty": 76.0, "price": 10.28, "ts": NOW + 2.5,
                                "order_id": trade["target_order_id"]}]
    legs = _legs(approved)
    stop = legs[trade["stop_order_id"]]
    assert (stop["qty"], stop["stop_price"], stop["status"]) == (77, 9.89, "Submitted")    # shrunk, never moved
    assert trade["stop"] == 9.89 and legs[trade["target2_order_id"]]["status"] == "Submitted"
    assert approved.broker.ledger.held_qty(SYM) == 77.0
    said = "Nova sold 76 at target 1 10.28; the stop 9.89 stays for the other 77"
    assert store.event(SYM)["text"] == said and said in mode_rows("half")[0]["reason"]

    approved.broker.try_fill_working(SYM, [(NOW + 4, 10.55)])          # target 2 sells the rest
    trade = tick(approved, NOW + 4.5)
    assert (trade["state"], trade["exit_reason"]) == ("closed", "target")
    assert [(h["leg"], h["qty"], h["price"]) for h in trade["halves"]] == [("target1", 76.0, 10.28),
                                                                            ("target2", 77.0, 10.50)]
    assert trade["exit_price"] == pytest.approx(round((76 * 10.28 + 77 * 10.50) / 153, 4))
    assert _legs(approved)[trade["stop_order_id"]]["status"] == "Cancelled"
    assert approved.broker.ledger.held_qty(SYM) == 0.0 and approved.broker.ledger.working_orders() == []
    text = store.event(SYM)["text"]
    assert "the target 2 10.50 filled" in text and "target 1 10.28 x 76, target 2 10.5 x 77" in text
    assert "+$56.72" in text                                             # 76 x 0.26 + 77 x 0.48: every share
    assert store.approval(SYM) is None


def test_the_stop_after_a_first_half_closes_the_trade_with_every_share_counted(approved):
    trade = holding(approved)
    approved.broker.try_fill_working(SYM, [(NOW + 2, 10.30)])
    tick(approved, NOW + 2.5)
    approved.broker.try_fill_working(SYM, [(NOW + 5, 9.85)])           # the stop sells the 77 left
    trade = tick(approved, NOW + 5.5)
    assert (trade["state"], trade["exit_reason"]) == ("closed", "stop")
    assert [(h["leg"], h["qty"], h["price"]) for h in trade["halves"]] == [("target1", 76.0, 10.28),
                                                                            ("stop", 77.0, 9.85)]
    legs = _legs(approved)
    assert (legs[trade["target2_order_id"]]["status"], legs[trade["target2_order_id"]]["reason_code"]) == (
        "Cancelled", "PRACTICE_OCO_CANCELLED")
    assert approved.broker.ledger.held_qty(SYM) == 0.0
    assert "+$6.67" in store.event(SYM)["text"]                          # 76 x 0.26 - 77 x 0.17


def test_taking_over_after_a_first_half_cancels_what_still_rests(approved):
    trade = holding(approved)
    approved.broker.try_fill_working(SYM, [(NOW + 2, 10.30)])
    tick(approved, NOW + 2.5)
    body = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(approved.key)).json()
    assert body["trade"]["exits"] == "you" and body["mode"] == "signal"
    legs = _legs(approved)
    assert legs[trade["target_order_id"]]["status"] == "Filled"           # the half that sold is never cancelled
    assert {legs[trade["target2_order_id"]]["status"], legs[trade["stop_order_id"]]["status"]} == {"Cancelled"}
    assert approved.broker.ledger.working_orders() == [] and approved.broker.ledger.held_qty(SYM) == 77.0


def test_the_view_carries_both_targets_and_the_halves(approved):
    trade = holding(approved)
    approved.broker.try_fill_working(SYM, [(NOW + 2, 10.30)])
    tick(approved, NOW + 2.5)
    shown = client.get(f"/api/stock-mode/{SYM}").json()["trade"]
    assert (shown["target"], shown["target2"], shown["target1_qty"], shown["target2_qty"]) == (10.28, 10.50, 76, 77)
    assert shown["target2_order_id"] == trade["target2_order_id"] and [h["leg"] for h in shown["halves"]] == ["target1"]
