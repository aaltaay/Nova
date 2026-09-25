"""Brackets on the practice venues (#606 step 1): Paper and Sim fill the shape Live sends.

Live sends IBKR's bracket -- a LMT entry, a take-profit LMT and a stop-loss STP
on the reverse side, three consecutive ids, the exits held until the entry fills
and then one-cancels-other. Paper and Sim used to refuse every bracket
(``SIM_NO_BRACKET``), so the ticket's default take-profit / stop-loss could not
be rehearsed where it costs nothing. These pin the rules the practice broker
follows now (``practice.bracket``): the ledger's events, the broker's fills,
cancels, replaces and expiries, and the Paper file across a restart.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from constants_practice import (
    PRACTICE_BUYING_POWER_CODE,
    PRACTICE_NO_LIVE_PRINT_CODE,
    PRACTICE_NO_SHORTS_CODE,
    PRACTICE_OCO_CANCELLED_CODE,
    PRACTICE_PARENT_CANCELLED_CODE,
    PRACTICE_PARENT_CANCELLED_REASON,
    PRACTICE_PARENT_EXPIRED_REASON,
    PRACTICE_SESSION_CLOSE_HOUR_ET,
    PRACTICE_TIF_EXPIRED_CODE,
)
from execution import telemetry
from practice import bracket, order_rules, persist
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from practice.clock import ET
from practice.ledger import EVENT_CANCELLED, EVENT_FILLED, EVENT_PLACED, Ledger
from sim.fill_model import Reference

MORNING = datetime(2026, 9, 21, 10, 0, tzinfo=ET)
NOW = MORNING.timestamp()
CLOSE = MORNING.replace(hour=PRACTICE_SESSION_CLOSE_HOUR_ET).timestamp()


class FakeLive:
    """The live feed as the Paper venue sees it: IMCC last 10.00 at 9.98 x 10.02, its own clock."""

    def __init__(self) -> None:
        self.now = NOW

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == "IMCC" else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == "IMCC" else (False, "dark", PRACTICE_NO_LIVE_PRINT_CODE)

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_for_tests()
    telemetry.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()
    telemetry.reset_for_tests()


def _resting(broker, **kw) -> dict:
    """100 IMCC: entry 9.90 under the 10.02 ask (it rests), target 10.50, stop 9.50."""
    return broker.place_bracket("IMCC", "BUY", 100, kw.pop("entry", 9.90), 10.50, 9.50, **kw)


def _filled(broker) -> dict:
    """100 IMCC: entry 10.05 over the 10.02 ask (it fills at once), target 10.50, stop 9.50."""
    return broker.place_bracket("IMCC", "BUY", 100, 10.05, 10.50, 9.50)


def _working(broker) -> dict[int, dict]:
    return {int(r["order_id"]): r for r in broker.working_orders()}


def _closed(broker) -> dict[int, dict]:
    return {int(r["order_id"]): r for r in broker.closed_orders()}


# ── the ledger: waking and closing are derived from, and recorded as, events ──

def _ledger_bracket() -> Ledger:
    ledger = Ledger(100_000, created_ts=NOW)
    entry = {
        "order_id": 1, "symbol": "IMCC", "side": "BUY", "qty": 100.0, "filled_qty": 0.0,
        "remaining_qty": 100.0, "order_type": "LMT", "limit_price": 9.90, "stop_price": None,
        "status": "Submitted", "placed_ts": NOW, "source": "nova", "order_source": "manual",
        "bot_id": None, **bracket.leg_fields(1, "parent"),
    }
    for row in (entry, *bracket.exit_rows(entry, 2, 3, 10.50, 9.50)):
        ledger.place(row, ts=NOW, source="manual")
    return ledger


def _state(ledger: Ledger) -> dict[int, tuple[str, float]]:
    return {int(r["order_id"]): (r["status"], r["placed_ts"]) for r in ledger.working_orders()}


def test_the_ledger_wakes_the_exits_at_the_entrys_fill_and_a_rewind_puts_them_back() -> None:
    ledger = _ledger_bracket()
    assert _state(ledger) == {1: ("Submitted", NOW), 2: ("PreSubmitted", NOW), 3: ("PreSubmitted", NOW)}

    ledger.fill(1, ts=NOW + 5, price=9.90, basis="print_cross")

    assert _state(ledger) == {2: ("Submitted", NOW + 5), 3: ("Submitted", NOW + 5)}
    # Waking is not an event: the fill is, and the exits follow from it.
    assert [e["type"] for e in ledger.events] == [EVENT_PLACED] * 3 + [EVENT_FILLED]
    assert ledger.unwind_to(NOW + 1) == 1
    assert _state(ledger) == {1: ("Submitted", NOW), 2: ("PreSubmitted", NOW), 3: ("PreSubmitted", NOW)}
    assert ledger.held_qty("IMCC") == 0


def test_a_rewind_before_the_one_cancels_other_restores_the_other_exit() -> None:
    ledger = _ledger_bracket()
    ledger.fill(1, ts=NOW + 5, price=9.90, basis="print_cross")
    ledger.fill(2, ts=NOW + 10, price=10.50, basis="print_cross")

    cancel = ledger.events[-1]
    assert (cancel["type"], cancel["ts"], cancel["order_id"], cancel["code"], cancel["source"]) == (
        EVENT_CANCELLED, NOW + 10, 3, PRACTICE_OCO_CANCELLED_CODE, "venue",
    )
    assert ledger.working_orders() == [] and ledger.held_qty("IMCC") == 0

    assert ledger.unwind_to(NOW + 7) == 2  # the target's fill and the cancel it caused
    assert _state(ledger) == {2: ("Submitted", NOW + 5), 3: ("Submitted", NOW + 5)}
    assert ledger.held_qty("IMCC") == 100
    copy = Ledger(ledger.starting_cash, created_ts=ledger.created_ts, events=ledger.events)
    assert copy.working_orders() == ledger.working_orders()


# ── placing ───────────────────────────────────────────────────────────────────

def test_a_bracket_is_three_consecutive_orders_in_lives_shape(paper) -> None:
    raw = _resting(paper.broker)

    assert (raw["ok"], raw["broker_status"], raw["mode"], raw["error"]) == (True, "Submitted", "paper", None)
    p = raw["parent_order_id"]
    assert (raw["order_id"], raw["target_order_id"], raw["stop_order_id"]) == (p, p + 1, p + 2)
    rows = _working(paper.broker)
    assert [
        (r["side"], r["qty"], r["order_type"], r["limit_price"], r["stop_price"], r["status"],
         r["leg_role"], r["parent_id"], r["oca_group"])
        for r in (rows[p], rows[p + 1], rows[p + 2])
    ] == [
        ("BUY", 100, "LMT", 9.90, None, "Submitted", "parent", None, None),
        ("SELL", 100, "LMT", 10.50, None, "PreSubmitted", "target", p, f"oca-{p}"),
        ("SELL", 100, "STP", None, 9.50, "PreSubmitted", "stop", p, f"oca-{p}"),
    ]
    assert {(r["tif"], r["expires_ts"], r["nova_placed_at"]) for r in rows.values()} == {
        ("DAY", CLOSE, raw["nova_placed_at"]),
    }
    plain = paper.broker.place("IMCC", "BUY", 1, "LMT", limit_price=9.0)
    row = _working(paper.broker)[plain["order_id"]]
    assert (row["parent_id"], row["oca_group"], row["leg_role"]) == (None, None, None)


def test_a_marketable_entry_fills_at_once_and_its_exits_rest_working(paper) -> None:
    raw = _filled(paper.broker)

    assert (raw["broker_status"], raw["avg_fill_price"], raw["filled_qty"]) == ("Filled", 10.02, 100)
    p = raw["parent_order_id"]
    assert _closed(paper.broker)[p]["fill_basis"] == "live_quote"
    rows = _working(paper.broker)
    assert [(rows[i]["status"], rows[i]["placed_ts"]) for i in (p + 1, p + 2)] == [("Submitted", NOW)] * 2
    assert paper.broker.positions()[0]["qty"] == 100


def test_a_short_bracket_is_refused_no_shorts(paper) -> None:
    for raw in (
        paper.broker.place_bracket("IMCC", "SELL", 100, 10.0, 9.5, 10.5, short_entry=True),
        paper.broker.place_bracket("IMCC", "SELL", 100, 10.0, 9.5, 10.5),
    ):
        assert (raw["ok"], raw["reason_code"], raw["parent_order_id"]) == (False, PRACTICE_NO_SHORTS_CODE, None)
    assert paper.broker.ledger.events == []
    # A SELL entry is a short entry even while shares are held: its exits would buy.
    paper.broker.place("IMCC", "BUY", 100, "MKT")
    raw = paper.broker.place_bracket("IMCC", "SELL", 100, 10.0, 9.5, 10.5)
    assert raw["reason_code"] == PRACTICE_NO_SHORTS_CODE and paper.broker.working_orders() == []


def test_buying_power_is_checked_at_the_entry_limit(paper) -> None:
    paper.broker.reset(30_000)  # 4x intraday: 120,000 of buying power

    # 11,500 at the 11.00 limit needs 126,500; at the 10.02 ask it would fit (115,230).
    raw = paper.broker.place_bracket("IMCC", "BUY", 11_500, 11.00, 11.50, 9.50)

    assert (raw["ok"], raw["reason_code"]) == (False, PRACTICE_BUYING_POWER_CODE)
    assert "needs 126,500.00, has 120,000.00" in raw["error"]
    assert paper.broker.working_orders() == [] and paper.broker.positions() == []
    fits = paper.broker.place_bracket("IMCC", "BUY", 10_000, 11.00, 11.50, 9.50)
    assert fits["broker_status"] == "Filled" and len(paper.broker.working_orders()) == 2


def test_a_bracket_the_door_would_refuse_is_refused_by_the_broker_too(paper) -> None:
    assert paper.broker.place_bracket("IMCC", "BUY", 100, 9.90, 9.50, 10.50)["reason_code"] == "BRACKET_GEOMETRY"
    assert paper.broker.place_bracket("IMCC", "BUY", 0, 9.90, 10.50, 9.50)["reason_code"] == "QTY_INVALID"
    assert _resting(paper.broker, tif="IOC")["reason_code"] == "TIF_INVALID"
    assert paper.broker.place_bracket("SPY", "BUY", 100, 9.90, 10.50, 9.50)["reason_code"] == PRACTICE_NO_LIVE_PRINT_CODE
    assert paper.broker.ledger.events == []


# ── filling ───────────────────────────────────────────────────────────────────

def test_waiting_exits_never_fill_before_their_entry(paper) -> None:
    raw = _resting(paper.broker)
    p = raw["parent_order_id"]

    # Through the target, above the entry: the target waits.
    assert paper.broker.try_fill_working("IMCC", [(NOW + 1, 10.60)]) == []
    # The operator lowers the entry under the stop, so a print can cross the
    # stop without filling the entry: the stop waits too.
    assert paper.broker.replace(p, limit_price=9.00)["broker_status"] == "Submitted"
    assert paper.broker.try_fill_working("IMCC", [(NOW + 2, 9.40)]) == []

    rows = _working(paper.broker)
    assert [rows[i]["status"] for i in (p, p + 1, p + 2)] == ["Submitted", "PreSubmitted", "PreSubmitted"]
    assert paper.broker.positions() == []


def test_the_print_that_fills_the_entry_never_fills_an_exit(paper) -> None:
    raw = _resting(paper.broker)
    p = raw["parent_order_id"]

    # 9.40 is through the entry and through the stop; so is a second print in the same second.
    filled = paper.broker.try_fill_working("IMCC", [(NOW + 1, 9.40), (NOW + 1, 9.30)])

    assert [(r["order_id"], r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(p, 9.90, "print_cross")]
    rows = _working(paper.broker)
    assert [(rows[i]["status"], rows[i]["placed_ts"]) for i in (p + 1, p + 2)] == [("Submitted", NOW + 1)] * 2
    filled = paper.broker.try_fill_working("IMCC", [(NOW + 2, 9.40)])
    assert [(r["order_id"], r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(p + 2, 9.40, "stop_trigger")]


@pytest.mark.parametrize(
    ("price", "fills", "cancels", "fill_price", "basis", "reason"),
    [
        (10.60, "target", "stop", 10.50, "print_cross", "One-cancels-other: the target filled"),
        (9.40, "stop", "target", 9.40, "stop_trigger", "One-cancels-other: the stop filled"),
    ],
)
def test_one_exit_filling_cancels_the_other(paper, price, fills, cancels, fill_price, basis, reason) -> None:
    raw = _filled(paper.broker)
    ids = {"target": raw["target_order_id"], "stop": raw["stop_order_id"]}

    filled = paper.broker.try_fill_working("IMCC", [(NOW + 1, price)])

    assert [(r["order_id"], r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(ids[fills], fill_price, basis)]
    other = _closed(paper.broker)[ids[cancels]]
    assert (other["status"], other["reason_code"], other["error"]) == ("Cancelled", PRACTICE_OCO_CANCELLED_CODE, reason)
    assert paper.broker.working_orders() == [] and paper.broker.positions() == []
    event = paper.broker.ledger.events[-1]
    assert (event["type"], event["ts"], event["source"]) == (EVENT_CANCELLED, NOW + 1, "venue")


def test_an_entry_the_venue_cancels_at_the_fill_takes_its_exits(paper, monkeypatch) -> None:
    raw = _resting(paper.broker)
    p = raw["parent_order_id"]
    monkeypatch.setattr(
        order_rules, "fill_refusal",
        lambda *_a, **_k: ("Not enough buying power at the fill", PRACTICE_BUYING_POWER_CODE),
    )

    assert paper.broker.try_fill_working("IMCC", [(NOW + 1, 9.80)]) == []

    closed = _closed(paper.broker)
    assert (closed[p]["status"], closed[p]["reason_code"]) == ("Cancelled", PRACTICE_BUYING_POWER_CODE)
    assert [closed[i]["reason_code"] for i in (p + 1, p + 2)] == [PRACTICE_PARENT_CANCELLED_CODE] * 2
    assert paper.broker.working_orders() == []


# ── cancelling and replacing ──────────────────────────────────────────────────

def test_cancelling_the_entry_cancels_the_exits_waiting_on_it(paper) -> None:
    raw = _resting(paper.broker)
    p = raw["parent_order_id"]

    assert paper.broker.cancel(p)["ok"] is True

    closed = _closed(paper.broker)
    assert (closed[p]["status"], closed[p].get("reason_code")) == ("Cancelled", None)
    assert [(closed[i]["status"], closed[i]["reason_code"], closed[i]["error"]) for i in (p + 1, p + 2)] == [
        ("Cancelled", PRACTICE_PARENT_CANCELLED_CODE, PRACTICE_PARENT_CANCELLED_REASON),
    ] * 2
    assert paper.broker.working_orders() == []


def test_cancelling_one_exit_leaves_the_other(paper) -> None:
    working = _filled(paper.broker)
    assert paper.broker.cancel(working["target_order_id"])["ok"] is True
    assert list(_working(paper.broker)) == [working["stop_order_id"]]

    waiting = _resting(paper.broker)
    assert paper.broker.cancel(waiting["stop_order_id"])["ok"] is True
    assert {oid: r["status"] for oid, r in _working(paper.broker).items()} == {
        working["stop_order_id"]: "Submitted",
        waiting["parent_order_id"]: "Submitted",
        waiting["target_order_id"]: "PreSubmitted",
    }


def test_cancelling_a_leg_its_bracket_already_closed_answers_gone_not_failed(paper) -> None:
    """KILL, the account flatten and cancel-all cancel a list of working orders one by one."""
    raw = _resting(paper.broker)
    paper.broker.cancel(raw["parent_order_id"])
    for leg in (raw["target_order_id"], raw["stop_order_id"]):
        out = paper.broker.cancel(leg)
        assert (out["ok"], out["verified_gone"], out["closed_by"]) == (True, True, PRACTICE_PARENT_CANCELLED_CODE)

    oco = _filled(paper.broker)
    paper.broker.try_fill_working("IMCC", [(NOW + 1, 10.60)])  # the target fills, the stop is cancelled
    assert paper.broker.cancel(oco["stop_order_id"])["closed_by"] == PRACTICE_OCO_CANCELLED_CODE
    # A leg that filled, and a plain order cancelled twice, are still not open: nothing changed there.
    assert paper.broker.cancel(oco["target_order_id"])["ok"] is False
    plain = paper.broker.place("IMCC", "BUY", 1, "LMT", limit_price=9.0)
    assert paper.broker.cancel(plain["order_id"])["ok"] is True
    assert paper.broker.cancel(plain["order_id"]) == {
        "ok": False, "error": f"order {plain['order_id']} not open", "verified_gone": True,
    }


def test_a_waiting_exit_can_be_repriced_and_still_waits(paper) -> None:
    raw = _resting(paper.broker)
    p, target = raw["parent_order_id"], raw["target_order_id"]

    # 9.00 is marketable against the 9.98 bid: a working SELL would fill at once.
    moved = paper.broker.replace(target, limit_price=9.00)

    assert (moved["ok"], moved["broker_status"]) == (True, "PreSubmitted")
    row = _working(paper.broker)[target]
    assert (row["limit_price"], row["status"], row["parent_id"], row["oca_group"], row["leg_role"]) == (
        9.00, "PreSubmitted", p, f"oca-{p}", "target",
    )
    # The entry fills and wakes it; it fills on the next print, at its new price.
    assert [r["order_id"] for r in paper.broker.try_fill_working("IMCC", [(NOW + 1, 9.80)])] == [p]
    filled = paper.broker.try_fill_working("IMCC", [(NOW + 2, 9.85)])
    assert [(r["order_id"], r["avg_fill_price"]) for r in filled] == [(target, 9.00)]


def test_repricing_the_entry_through_the_market_fills_it_and_wakes_the_exits(paper) -> None:
    raw = _resting(paper.broker)
    p = raw["parent_order_id"]

    moved = paper.broker.replace(p, limit_price=10.05)  # over the 10.02 ask

    assert (moved["broker_status"], moved["avg_fill_price"]) == ("Filled", 10.02)
    assert {oid: (r["status"], r["placed_ts"]) for oid, r in _working(paper.broker).items()} == {
        p + 1: ("Submitted", NOW), p + 2: ("Submitted", NOW),
    }


# ── expiry ────────────────────────────────────────────────────────────────────

def test_an_entry_that_expires_unfilled_takes_its_exits_along(paper) -> None:
    raw = _resting(paper.broker)
    p = raw["parent_order_id"]
    paper.ref.now = CLOSE

    expired = paper.broker.expire_due()

    assert [(r["order_id"], r["status"], r["reason_code"]) for r in expired] == [
        (p, "Expired", PRACTICE_TIF_EXPIRED_CODE),
    ]
    closed = _closed(paper.broker)
    assert [(closed[i]["status"], closed[i]["reason_code"], closed[i]["error"]) for i in (p + 1, p + 2)] == [
        ("Cancelled", PRACTICE_PARENT_CANCELLED_CODE, PRACTICE_PARENT_EXPIRED_REASON),
    ] * 2
    assert paper.broker.working_orders() == []


def test_working_exits_expire_on_their_own_and_a_gtc_bracket_never_does(paper) -> None:
    day = _filled(paper.broker)
    gtc = _resting(paper.broker, tif="GTC")
    paper.ref.now = CLOSE

    expired = paper.broker.expire_due()

    assert sorted((r["order_id"], r["status"], r["reason_code"]) for r in expired) == [
        (day["target_order_id"], "Expired", PRACTICE_TIF_EXPIRED_CODE),
        (day["stop_order_id"], "Expired", PRACTICE_TIF_EXPIRED_CODE),
    ]
    assert paper.broker.positions()[0]["qty"] == 100  # only the exits expired
    assert sorted(_working(paper.broker)) == [gtc["parent_order_id"], gtc["target_order_id"], gtc["stop_order_id"]]
    paper.ref.now = CLOSE + 3 * 86_400
    assert paper.broker.expire_due() == []


# ── the watches and the Paper file ────────────────────────────────────────────

def test_every_leg_a_bracket_closes_has_its_watch_told(paper) -> None:
    raw = _resting(paper.broker)
    paper.broker.cancel(raw["parent_order_id"])  # the cancel's send path answers for the entry itself
    for leg in (raw["target_order_id"], raw["stop_order_id"]):
        assert telemetry.watch_order(leg).latest_status == "Cancelled"

    oco = _filled(paper.broker)
    paper.broker.try_fill_working("IMCC", [(NOW + 1, 9.40)])
    assert telemetry.watch_order(oco["stop_order_id"]).latest_status == "Filled"
    assert telemetry.watch_order(oco["target_order_id"]).latest_status == "Cancelled"


def test_a_bracket_survives_a_restart_and_keeps_working(paper) -> None:
    raw = _resting(paper.broker)
    p = raw["parent_order_id"]

    reset_for_tests()  # the next process reloads practice-paper.json
    again = for_venue("paper")

    assert {oid: (r["status"], r["leg_role"], r["parent_id"], r["oca_group"]) for oid, r in _working(again).items()} == {
        p: ("Submitted", "parent", None, None),
        p + 1: ("PreSubmitted", "target", p, f"oca-{p}"),
        p + 2: ("PreSubmitted", "stop", p, f"oca-{p}"),
    }
    assert [r["order_id"] for r in again.try_fill_working("IMCC", [(NOW + 1, 9.80)])] == [p]
    assert {r["status"] for r in again.working_orders()} == {"Submitted"}


def test_a_ledger_written_before_brackets_loads_and_trades() -> None:
    old_row = {
        "order_id": 7, "perm_id": 7, "symbol": "IMCC", "side": "BUY", "qty": 10.0, "filled_qty": 0.0,
        "remaining_qty": 10.0, "order_type": "LMT", "limit_price": 9.5, "stop_price": None,
        "status": "Submitted", "placed_ts": NOW, "source": "nova", "order_source": "manual", "bot_id": None,
    }
    ledger = persist.from_dict({
        "schema_version": 1, "starting_cash": 100_000.0, "created_ts": NOW,
        "events": [{"type": EVENT_PLACED, "ts": NOW, "source": "manual", "bot_id": None, "row": old_row}],
    })

    row = ledger.working_orders()[0]
    assert "leg_role" not in row and not bracket.is_waiting(row)
    assert ledger.fill(7, ts=NOW + 1, price=9.5, basis="print_cross")["status"] == "Filled"
    assert len(ledger.events) == 2  # nothing closed with it

    bracketed = _ledger_bracket()
    bracketed.fill(1, ts=NOW + 5, price=9.90, basis="print_cross")
    reloaded = persist.from_dict(persist.to_dict(bracketed))
    assert reloaded.working_orders() == bracketed.working_orders()
    assert reloaded.snapshot("paper") == bracketed.snapshot("paper")
