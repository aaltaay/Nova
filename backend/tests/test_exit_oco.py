"""The exit-only one-cancels-other pair through the execution door (#681).

For shares the venue already holds: a stop for every share and one or two targets, committed once. The
stop's fill cancels the targets; a target's fill shrinks the stop to the shares left, at the same price;
nothing sells twice or past flat. These run the real door (``execution.service.execute``) on a Paper
broker priced by a fake live market, and the Sim scratch account on a loaded replay for the rewind.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from constants_practice import EXIT_OCO_LIVE_CODE, PRACTICE_OCO_CANCELLED_CODE
from execution import exit_oco, flatten_intent, inflight, service, store
from execution.models import ExecutionCommand
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

NOW = 1_790_000_000.0         # 2026-09-21 10:13 ET: regular hours (a MKT may fill)
SYM = "IMCC"


class FakeLive:
    """A live market that prices IMCC at 9.98 x 10.02 (last 10.00) and never prints on its own."""

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == SYM else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYM else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return NOW

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


@pytest.fixture
def paper(monkeypatch):
    """Paper, armed, holding 100 IMCC bought at the 10.02 ask."""
    reset_venue()
    reset_for_tests()
    service.reset_for_tests()
    store.init_db()
    monkeypatch.setattr(practice_broker, "LiveReference", FakeLive)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    broker = for_venue("paper")
    broker.place(SYM, "BUY", 100, "MKT")
    yield SimpleNamespace(broker=broker)
    service.reset_for_tests()
    inflight.reset_for_tests()
    reset_for_tests()
    reset_venue()


def pair(key: str = "pair", **kw) -> ExecutionCommand:
    """SELL 100: stop 9.80, target 1 10.30 for 50, target 2 10.60 for the other 50."""
    base = dict(operation="exit_oco", idempotency_key=key, source="manual", origin="nova_exit", symbol=SYM,
                side="SELL", qty=100, order_type="STP", stop_price=9.80, target_price=10.30, target2_price=10.60,
                target1_qty=50, skip_risk=True)
    base.update(kw)
    return ExecutionCommand(**base)


def sell(key: str, qty: float = 10) -> ExecutionCommand:
    return ExecutionCommand(operation="place", idempotency_key=key, source="manual", symbol=SYM, side="SELL",
                            qty=qty, order_type="LMT", limit_price=10.50, skip_risk=True)


def row(p, oid) -> dict:
    return p.broker.ledger.order_row(int(oid))


# -- the halves ----------------------------------------------------------------------------
@pytest.mark.parametrize("qty, t2, fraction, want", [
    (100, 10.6, None, (50, 50)),
    (101, 10.6, 0.5, (50, 51)),          # an odd count: the first half the smaller part
    (3, 10.6, None, (1, 2)),
    (1, 10.6, None, (1, 0)),             # one share sells whole at target 1
    (100, None, None, (100, 0)),         # no target 2: every share at target 1, as before
    (100, 10.2, None, (100, 0)),         # a target 2 not beyond target 1 is no second half
    (100, 10.6, 0.25, (25, 75)),
    (100, 10.6, 1.5, (50, 50)),          # not a fraction: half
])
def test_a_position_splits_into_its_halves(qty, t2, fraction, want) -> None:
    assert exit_oco.split(qty, 10.3, t2, fraction) == want


def test_a_shorts_second_target_is_under_the_first() -> None:
    assert exit_oco.split(100, 9.5, 9.2, short=True) == (50, 50)
    assert exit_oco.split(100, 9.5, 9.8, short=True) == (100, 0)


# -- committed once -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_pair_is_committed_once_and_answers_its_three_ids(paper) -> None:
    receipt = await service.execute(pair())
    assert receipt.ok is True, receipt.error
    stop, t1, t2 = receipt.stop_order_id, receipt.target_order_id, receipt.target2_order_id
    assert receipt.order_id == stop and (t1, t2) == (stop + 1, stop + 2)
    assert receipt.legacy_place_dict()["target2_order_id"] == t2
    assert (row(paper, stop)["order_type"], row(paper, stop)["stop_price"], row(paper, stop)["qty"]) == ("STP", 9.80, 100)
    assert (row(paper, t1)["limit_price"], row(paper, t1)["qty"], row(paper, t1)["leg_role"]) == (10.30, 50, "target")
    assert (row(paper, t2)["limit_price"], row(paper, t2)["qty"], row(paper, t2)["leg_role"]) == (10.60, 50, "target2")
    assert {row(paper, i)["oca_group"] for i in (stop, t1, t2)} == {f"oca-{stop}"}
    assert {row(paper, i)["order_origin"] for i in (stop, t1, t2)} == {"nova_exit"}
    # One commitment for every share: the pair's legs sell the same shares.
    held = inflight.snapshot("paper")
    assert [(c["side"], c["qty"], c["order_id"]) for c in held] == [("SELL", 100.0, stop)]
    assert store.get_by_id(receipt.execution_id)["payload"]["target2_order_id"] == t2
    # The ticket's Flatten counts the group once: everything is already being closed.
    assert flatten_intent.closing_committed(SYM, "SELL")[0] == 100.0


@pytest.mark.asyncio
async def test_an_unrelated_second_sell_of_the_same_shares_is_still_refused(paper) -> None:
    assert (await service.execute(pair())).ok
    second = await service.execute(sell("again", 10))
    assert second.ok is False and second.reason_code == "OVERSELL"
    assert "100.0 already sent" in second.error
    again = await service.execute(pair("pair-2"))
    assert again.ok is False and again.reason_code == "OVERSELL"


@pytest.mark.asyncio
async def test_a_pair_past_what_is_held_or_with_nothing_held_is_refused(paper) -> None:
    over = await service.execute(pair(qty=150, target1_qty=75))
    assert over.ok is False and over.reason_code == "OVERSELL"
    cover = await service.execute(pair("cover", side="BUY", stop_price=10.40, target_price=9.70, target2_price=9.40))
    assert cover.ok is False and cover.reason_code == "NO_POSITION"
    assert paper.broker.ledger.working_orders() == []


@pytest.mark.parametrize("bad, code", [
    (dict(stop_price=10.40), "EXIT_OCO_GEOMETRY"),             # the stop over target 1
    (dict(target2_price=10.20), "EXIT_OCO_GEOMETRY"),          # target 2 under target 1
    (dict(target1_qty=100), "EXIT_OCO_FIELDS"),                # no shares left for target 2
    (dict(target1_qty=None), "EXIT_OCO_FIELDS"),
    (dict(target_price=None), "EXIT_OCO_FIELDS"),
    (dict(source="flatten"), "EXIT_OCO_FIELDS"),
    (dict(good_for_sec=3.0), "EXIT_OCO_FIELDS"),
    (dict(qty=100.5), "QTY_FRACTIONAL_API"),
])
@pytest.mark.asyncio
async def test_a_pair_that_does_not_hang_together_is_refused(paper, bad, code) -> None:
    receipt = await service.execute(pair(f"bad-{code}-{sorted(bad)}", **bad))
    assert receipt.ok is False and receipt.reason_code == code, receipt.error
    assert paper.broker.ledger.working_orders() == [] and inflight.snapshot("paper") == []


# -- the first fill cancels or reduces the others -------------------------------------------
@pytest.mark.asyncio
async def test_target_one_shrinks_the_stop_and_the_stop_sells_the_rest(paper) -> None:
    r = await service.execute(pair())
    stop, t1, t2 = r.stop_order_id, r.target_order_id, r.target2_order_id
    paper.broker.try_fill_working(SYM, [(NOW + 5, 10.35)])               # target 1
    assert row(paper, t1)["status"] == "Filled" and paper.broker.ledger.held_qty(SYM) == 50
    s = row(paper, stop)
    assert (s["status"], s["qty"], s["remaining_qty"], s["stop_price"]) == ("Submitted", 50, 50, 9.80)
    assert row(paper, t2)["status"] == "Submitted"
    # The shares left are still committed: another SELL of them is refused.
    refused = await service.execute(sell("after-half", 10))
    assert refused.ok is False and refused.reason_code == "OVERSELL"
    paper.broker.try_fill_working(SYM, [(NOW + 9, 9.75)])                # the stop, for the 50 left
    assert row(paper, stop)["status"] == "Filled" and row(paper, stop)["filled_qty"] == 50
    assert (row(paper, t2)["status"], row(paper, t2)["reason_code"]) == ("Cancelled", PRACTICE_OCO_CANCELLED_CODE)
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and paper.broker.ledger.working_orders() == []
    assert inflight.snapshot("paper") == []                              # the stop's close freed it


@pytest.mark.asyncio
async def test_both_targets_sell_every_share_and_spend_the_stop(paper) -> None:
    r = await service.execute(pair())
    paper.broker.try_fill_working(SYM, [(NOW + 5, 10.35), (NOW + 6, 10.65)])
    s = row(paper, r.stop_order_id)
    assert (s["status"], s["reason_code"]) == ("Cancelled", PRACTICE_OCO_CANCELLED_CODE)
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and paper.broker.ledger.working_orders() == []
    assert inflight.snapshot("paper") == []


@pytest.mark.asyncio
async def test_the_stop_first_cancels_both_targets(paper) -> None:
    r = await service.execute(pair())
    paper.broker.try_fill_working(SYM, [(NOW + 5, 9.70)])
    assert row(paper, r.stop_order_id)["filled_qty"] == 100
    for oid in (r.target_order_id, r.target2_order_id):
        assert (row(paper, oid)["status"], row(paper, oid)["reason_code"]) == ("Cancelled", PRACTICE_OCO_CANCELLED_CODE)
    assert paper.broker.ledger.held_qty(SYM) == 0.0


@pytest.mark.asyncio
async def test_one_target_for_every_share_cancels_the_stop_like_a_bracket(paper) -> None:
    r = await service.execute(pair(target2_price=None, target1_qty=None))
    assert r.ok and r.target2_order_id is None and row(paper, r.target_order_id)["qty"] == 100
    paper.broker.try_fill_working(SYM, [(NOW + 5, 10.35)])
    s = row(paper, r.stop_order_id)
    assert (s["status"], s["qty"], s["reason_code"]) == ("Cancelled", 100, PRACTICE_OCO_CANCELLED_CODE)
    assert paper.broker.ledger.held_qty(SYM) == 0.0


@pytest.mark.asyncio
async def test_a_raise_moves_the_stop_alone_and_keeps_the_pair(paper) -> None:
    r = await service.execute(pair())
    moved = await service.execute(ExecutionCommand(operation="replace", idempotency_key="raise", source="manual",
                                                   order_id=r.stop_order_id, symbol=SYM, stop_price=9.95,
                                                   skip_risk=True))
    assert moved.ok, moved.error
    assert row(paper, r.stop_order_id)["stop_price"] == 9.95 and row(paper, r.stop_order_id)["oca_group"]
    paper.broker.try_fill_working(SYM, [(NOW + 5, 10.35), (NOW + 6, 9.90)])
    assert row(paper, r.stop_order_id)["filled_qty"] == 50 and paper.broker.ledger.held_qty(SYM) == 0.0


# -- a short's cover mirrors it -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_shorts_pair_covers_in_halves(paper, short_market_open) -> None:
    paper.broker.place(SYM, "SELL", 100, "MKT")                       # flat
    raw = paper.broker.place(SYM, "SELL", 100, "LMT", limit_price=9.98, short_entry=True)
    assert raw["ok"] and paper.broker.ledger.held_qty(SYM) == -100
    r = await service.execute(pair("cover", side="BUY", stop_price=10.40, target_price=9.70, target2_price=9.40))
    assert r.ok, r.error
    assert [(c["side"], c["qty"]) for c in inflight.snapshot("paper")] == [("BUY", 100.0)]
    over = await service.execute(ExecutionCommand(operation="place", idempotency_key="cover-more", source="manual",
                                                  symbol=SYM, side="BUY", qty=10, order_type="LMT",
                                                  limit_price=9.90, skip_risk=True))
    assert over.ok is False and over.reason_code == "OVERCOVER"
    paper.broker.try_fill_working(SYM, [(NOW + 5, 9.65)])                # target 1 covers 50
    s = row(paper, r.stop_order_id)
    assert (s["side"], s["qty"], s["stop_price"]) == ("BUY", 50, 10.40) and paper.broker.ledger.held_qty(SYM) == -50
    paper.broker.try_fill_working(SYM, [(NOW + 9, 10.45)])               # the buy stop covers the rest
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and paper.broker.ledger.working_orders() == []


# -- Live waits on its proof ------------------------------------------------------------------
def test_live_refuses_the_pair_and_a_bracket_in_halves(paper, monkeypatch) -> None:
    from execution import validate

    monkeypatch.setattr(validate, "_practice", lambda venue: False)
    ok, _detail, code = validate.validate_command(pair(), venue="live")
    assert (ok, code) == (False, EXIT_OCO_LIVE_CODE)
    bracket = ExecutionCommand(operation="bracket", idempotency_key="b", source="bot", symbol=SYM, side="BUY",
                               qty=100, order_type="LMT", limit_price=10.0, entry_price=10.0, target_price=10.3,
                               target2_price=10.6, target1_qty=50, stop_price=9.8)
    ok, _detail, code = validate.validate_command(bracket, venue="live")
    assert (ok, code) == (False, EXIT_OCO_LIVE_CODE)
