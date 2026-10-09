"""A practice order's own expiry (#816, ADR 052 amendment): ``ExecutionCommand.good_for_sec``.

The practice broker turns ``good_for_sec`` into the row's ``expires_ts`` -- the earlier of the TIF's
close and the placement plus the seconds -- and expires the order there as a DAY order at the close:
an ``expired`` event at its own second (``PRACTICE_GOOD_FOR_EXPIRED``), never filled by a later print.
A bracket's exits keep the TIF's close. A cancel that reaches an order already past its expiry records
the expiry. The execution door refuses a bad value and refuses the field on Live; Nova's bot sends it on
a Sim replay only, so Paper is unchanged.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from constants_practice import (
    GOOD_FOR_LIVE_CODE,
    PRACTICE_GOOD_FOR_EXPIRED_CODE,
    PRACTICE_GOOD_FOR_INVALID_CODE,
    PRACTICE_ORDER_STATUS_EXPIRED,
    PRACTICE_PARENT_CANCELLED_CODE,
    PRACTICE_PARENT_GOOD_FOR_EXPIRED_REASON,
    PRACTICE_SESSION_CLOSE_HOUR_ET,
    PRACTICE_TIF_EXPIRED_CODE,
)
from execution import inflight, service, store
from execution.models import ExecutionCommand
from execution.order_outcome import ledger_close
from execution.record_payload import build_reserve_payload
from execution.validate import validate_command
from ibkr import safety as _safety
from practice import broker as practice_broker, order_rules
from practice.broker import for_venue, reset_for_tests
from practice.clock import ET
from practice.ledger import EVENT_EXPIRED
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

SYM = "IMCC"
NOW = datetime(2026, 9, 21, 10, 0, tzinfo=ET).timestamp()
CLOSE = datetime(2026, 9, 21, PRACTICE_SESSION_CLOSE_HOUR_ET, 0, tzinfo=ET).timestamp()


class FakeLive:
    """IMCC quoted 9.98 x 10.02 on Paper's live feed, with a clock the test moves."""

    def __init__(self) -> None:
        self.now = NOW

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == SYM else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYM else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_venue()
    reset_for_tests()
    service.reset_for_tests()
    store.init_db()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    service.reset_for_tests()
    inflight.reset_for_tests()
    reset_for_tests()
    reset_venue()


# -- the rules -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [None, 3, 0.5, "2"])
def test_good_for_takes_seconds_above_zero(value) -> None:
    assert order_rules.good_for_error(value) is None


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), "soon", True, [3]])
def test_good_for_refuses_anything_else(value) -> None:
    assert order_rules.good_for_error(value) is not None


def test_the_expiry_is_the_earlier_of_the_tifs_and_the_placement_plus_the_seconds() -> None:
    day = {"placed_ts": NOW, "expires_ts": CLOSE}
    assert order_rules.good_for_fields(day, 3) == {"good_for_sec": 3.0, "expires_ts": NOW + 3}
    assert order_rules.good_for_fields(day, CLOSE - NOW + 60) == {"good_for_sec": CLOSE - NOW + 60, "expires_ts": CLOSE}
    assert order_rules.good_for_fields({"placed_ts": NOW, "expires_ts": None}, 3)["expires_ts"] == NOW + 3  # GTC
    assert order_rules.good_for_fields(day, None) == {"good_for_sec": None}                                 # the TIF's


# -- the Paper broker ----------------------------------------------------------------------------------------
def test_an_order_with_good_for_expires_at_its_own_second_and_no_later_print_fills_it(paper) -> None:
    raw = paper.broker.place(SYM, "BUY", 10, "LMT", limit_price=9.5, good_for_sec=3)
    oid = raw["order_id"]
    [row] = paper.broker.working_orders()
    assert (row["good_for_sec"], row["expires_ts"], row["tif"]) == (3.0, NOW + 3, "DAY")
    assert paper.broker.try_fill_working(SYM, [(NOW + 3.5, 9.4)]) == []          # after its second: never
    paper.ref.now = NOW + 2.9
    assert paper.broker.expire_due() == []
    paper.ref.now = NOW + 60
    [expired] = paper.broker.expire_due()
    assert (expired["order_id"], expired["status"], expired["reason_code"], expired["error"]) == (
        oid, PRACTICE_ORDER_STATUS_EXPIRED, PRACTICE_GOOD_FOR_EXPIRED_CODE, "Expired unfilled: its 3 s ran out",
    )
    event = paper.broker.ledger.events[-1]
    assert (event["type"], event["ts"]) == (EVENT_EXPIRED, NOW + 3)               # its own second, not the pass's


def test_a_print_inside_the_seconds_still_fills_it(paper) -> None:
    paper.broker.place(SYM, "BUY", 10, "LMT", limit_price=9.5, good_for_sec=3)
    [filled] = paper.broker.try_fill_working(SYM, [(NOW + 3, 9.4)])
    assert filled["status"] == "Filled"


def test_seconds_past_the_close_leave_the_day_expiry_and_its_reason(paper) -> None:
    paper.broker.place(SYM, "BUY", 10, "LMT", limit_price=9.5, good_for_sec=CLOSE - NOW + 600)
    assert paper.broker.working_orders()[0]["expires_ts"] == CLOSE
    paper.ref.now = CLOSE
    assert paper.broker.expire_due()[0]["reason_code"] == PRACTICE_TIF_EXPIRED_CODE


def test_a_gtc_order_with_good_for_expires_at_its_seconds(paper) -> None:
    paper.broker.place(SYM, "BUY", 10, "LMT", limit_price=9.5, tif="GTC", good_for_sec=5)
    assert paper.broker.working_orders()[0]["expires_ts"] == NOW + 5


def test_a_bad_good_for_is_refused_before_the_ledger_is_touched(paper) -> None:
    raw = paper.broker.place(SYM, "BUY", 10, "LMT", limit_price=9.5, good_for_sec=0)
    bracket = paper.broker.place_bracket(SYM, "BUY", 10, 9.9, 10.5, 9.5, good_for_sec=-3)
    assert raw["reason_code"] == bracket["reason_code"] == PRACTICE_GOOD_FOR_INVALID_CODE
    assert paper.broker.ledger.events == []


def test_a_brackets_entry_takes_the_seconds_and_its_exits_keep_the_close(paper) -> None:
    raw = paper.broker.place_bracket(SYM, "BUY", 10, 9.9, 10.5, 9.5, good_for_sec=3)
    rows = {r["order_id"]: r for r in paper.broker.working_orders()}
    entry, target, stop = rows[raw["parent_order_id"]], rows[raw["target_order_id"]], rows[raw["stop_order_id"]]
    assert (entry["good_for_sec"], entry["expires_ts"]) == (3.0, NOW + 3)
    assert {(r["good_for_sec"], r["expires_ts"]) for r in (target, stop)} == {(None, CLOSE)}

    paper.ref.now = NOW + 10
    paper.broker.expire_due()
    closed = {r["order_id"]: r for r in paper.broker.closed_orders()}
    assert closed[entry["order_id"]]["reason_code"] == PRACTICE_GOOD_FOR_EXPIRED_CODE
    for leg in (target, stop):                                                     # the entry takes them along
        assert (closed[leg["order_id"]]["reason_code"], closed[leg["order_id"]]["error"]) == (
            PRACTICE_PARENT_CANCELLED_CODE, PRACTICE_PARENT_GOOD_FOR_EXPIRED_REASON,
        )


def test_exits_of_an_entry_that_filled_inside_its_seconds_rest_past_them(paper) -> None:
    raw = paper.broker.place_bracket(SYM, "BUY", 10, 9.9, 10.5, 9.5, good_for_sec=3)
    paper.broker.try_fill_working(SYM, [(NOW + 1, 9.89)])                          # the entry fills; exits wake
    paper.ref.now = NOW + 600
    assert paper.broker.expire_due() == []
    assert {r["order_id"] for r in paper.broker.working_orders()} == {raw["target_order_id"], raw["stop_order_id"]}


def test_a_cancel_that_reaches_an_order_past_its_expiry_records_the_expiry(paper) -> None:
    raw = paper.broker.place_bracket(SYM, "BUY", 10, 9.9, 10.5, 9.5, good_for_sec=3)
    paper.ref.now = NOW + 90                                                       # no expiry pass has run yet
    answer = paper.broker.cancel(raw["parent_order_id"], source="bot")
    assert (answer["ok"], answer["verified_gone"], answer["closed_by"]) == (True, True, PRACTICE_GOOD_FOR_EXPIRED_CODE)
    entry = paper.broker.ledger.order_row(raw["parent_order_id"])
    assert entry["status"] == PRACTICE_ORDER_STATUS_EXPIRED
    assert [(e["type"], e["ts"]) for e in paper.broker.ledger.events if e.get("order_id") == raw["parent_order_id"]][-1] \
        == (EVENT_EXPIRED, NOW + 3)
    assert paper.broker.working_orders() == []


def test_a_cancel_inside_the_seconds_is_an_ordinary_cancel(paper) -> None:
    raw = paper.broker.place(SYM, "BUY", 10, "LMT", limit_price=9.5, good_for_sec=3)
    paper.ref.now = NOW + 1
    answer = paper.broker.cancel(raw["order_id"])
    assert answer["ok"] and "closed_by" not in answer
    assert paper.broker.ledger.order_row(raw["order_id"])["status"] == "Cancelled"


# -- the execution door ----------------------------------------------------------------------------------------
def _bracket(key: str, **over) -> ExecutionCommand:
    fields = dict(operation="bracket", idempotency_key=key, source="bot", symbol=SYM, side="BUY", qty=10,
                  order_type="LMT", limit_price=9.9, entry_price=9.9, target_price=10.5, stop_price=9.5,
                  skip_risk=True)
    fields.update(over)
    return ExecutionCommand(**fields)


def test_the_door_refuses_a_bad_value_and_refuses_the_field_on_live(paper, monkeypatch) -> None:
    assert validate_command(_bracket("bad", good_for_sec=0), venue="paper")[2] == PRACTICE_GOOD_FOR_INVALID_CODE
    assert validate_command(_bracket("ok", good_for_sec=3), venue="paper")[0] is True
    monkeypatch.setattr(_safety, "assert_armed_for", lambda source: (True, "OK"))
    ok, detail, code = validate_command(_bracket("live", good_for_sec=3), venue="live")
    assert (ok, code) == (False, GOOD_FOR_LIVE_CODE) and "Live" in detail


def test_cancel_and_replace_ignore_it() -> None:
    cancel = ExecutionCommand(operation="cancel", idempotency_key="c", source="bot", order_id=5, good_for_sec=0)
    assert validate_command(cancel, venue="paper")[0] is True


@pytest.mark.asyncio
async def test_an_entry_sent_through_the_door_expires_and_its_row_reads_cancelled(paper) -> None:
    placed = await service.execute(_bracket("good-for-entry", good_for_sec=3))
    assert placed.ok
    paper.broker.expire_due(now=NOW + 30)
    row = store.get_by_id(placed.execution_id)
    assert (row["status"], row["broker_status"], row["reason_code"], row["error"]) == (
        "cancelled", PRACTICE_ORDER_STATUS_EXPIRED, PRACTICE_GOOD_FOR_EXPIRED_CODE, None,
    )


@pytest.mark.asyncio
async def test_a_late_cancel_keeps_the_place_rows_expiry(paper) -> None:
    placed = await service.execute(_bracket("good-for-late-cancel", good_for_sec=3))
    paper.ref.now = NOW + 30
    cancel = await service.execute(ExecutionCommand(
        operation="cancel", idempotency_key="good-for-late-cancel:x", source="bot",
        order_id=placed.parent_order_id or placed.order_id, symbol=SYM, skip_risk=True,
    ))
    assert cancel.ok
    row = store.get_by_id(placed.execution_id)
    assert (row["status"], row["broker_status"], row["reason_code"]) == (
        "cancelled", PRACTICE_ORDER_STATUS_EXPIRED, PRACTICE_GOOD_FOR_EXPIRED_CODE,
    )


def test_the_expiry_is_a_close_not_a_refusal() -> None:
    assert ledger_close(PRACTICE_ORDER_STATUS_EXPIRED, reason_code=PRACTICE_GOOD_FOR_EXPIRED_CODE)["status"] == "cancelled"


def test_the_record_keeps_it_beside_the_tif(paper) -> None:
    payload = build_reserve_payload(_bracket("rec", good_for_sec=3), requested_qty=10, sent_qty=10,
                                    requested_price=9.9, measurement={}, forced_one_share=False, venue="paper")
    assert (payload["tif"], payload["good_for_sec"]) == ("DAY", 3)


# -- Nova's bot: on a replay only ---------------------------------------------------------------------------------
def test_the_bot_sends_its_ttl_on_a_replay_and_nothing_on_paper() -> None:
    from bot.first_pullback import orders

    assert orders.good_for({"replay_key": ["historical", SYM, "2026-09-18", "07:00", "10:00"],
                            "entry_ttl_sec": 3}) == 3.0
    assert orders.good_for({"replay_key": None, "entry_ttl_sec": 3}) is None


@pytest.mark.asyncio
async def test_the_bots_paper_entry_is_unchanged(paper) -> None:
    from bot.first_pullback import orders

    trade = {"venue": "paper", "setup_id": "IMCC-paper", "symbol": SYM, "qty": 1, "entry_planned": 9.90,
             "target1": 10.50, "stop": 9.50, "setup_type": "first_pullback", "entry_ttl_sec": 3}
    placed = await orders.place_entry(trade)
    entry = paper.broker.ledger.order_row(placed.parent_order_id)
    assert (entry["good_for_sec"], entry["expires_ts"]) == (None, CLOSE)
