"""Live's day cover, its short-entry cutoff and the alarm (ADR 048 decision 5, step 6).

While ``IBKR_SHORT_ENABLED`` is on, a Live short due its cover is covered at market in the regular session:
the stock's working Live orders are cancelled first, then one market BUY the door checks against IBKR's own
position -- sent to Live whatever the desk shows. A cover that cannot go out raises the alarm every desk
window shows. With the switch off Nova places nothing on Live. ``IBKR_SHORT_ENABLED`` is never set by a test:
``ibkr.safety.short_enabled`` is mocked.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import execution.service as exec_svc
from execution import inflight, store, telemetry
from execution.models import ExecutionCommand, ExecutionReceipt
from ibkr import client as client_mod
from ibkr import live_book
from ibkr import safety as safety_mod
from short_sale import cover_alarm, live_closes

ET = ZoneInfo("America/New_York")


def _at(hour: int, minute: int, day: int = 7) -> float:
    return datetime(2026, 10, day, hour, minute, tzinfo=ET).timestamp()


class Door:
    """The execution door as Live's closes call it: every command recorded, each answered as set."""

    def __init__(self) -> None:
        self.calls: list[ExecutionCommand] = []
        self.refuse: dict[str, str] = {}        # "cancel" | "place" -> the error

    async def execute(self, cmd: ExecutionCommand, **_kw) -> ExecutionReceipt:
        self.calls.append(cmd)
        error = self.refuse.get(cmd.operation)
        return ExecutionReceipt(ok=error is None, execution_id=f"e{len(self.calls)}", operation=cmd.operation,
                                source=cmd.source, idempotency_key=cmd.idempotency_key, error=error,
                                reason_code="BROKER_REJECT" if error else None,
                                order_id=None if error else 900 + len(self.calls))


@pytest.fixture
def live(monkeypatch):
    """IBKR ready with RDYN 400 short and its buy stop working; shorts on; Live's closes reset."""
    live_closes.reset_for_tests()
    cover_alarm.reset_for_tests()
    book = SimpleNamespace(positions={"RDYN": -400.0, "AAPL": 10.0},
                           rows=[{"order_id": 41, "symbol": "RDYN", "side": "BUY", "order_type": "STP",
                                  "remaining_qty": 400}], ready=True, mode="live", kind="live", states={})
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: book.ready)
    monkeypatch.setattr(client_mod, "account_mode", lambda: book.mode if book.ready else "disconnected")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: book.kind if book.ready else "unknown")
    monkeypatch.setattr(client_mod, "get_ib", lambda: object() if book.ready else None)
    monkeypatch.setattr(live_book, "positions", lambda: dict(book.positions))
    monkeypatch.setattr(live_book, "open_rows", lambda: [dict(r) for r in book.rows])
    monkeypatch.setattr(live_book, "order_state", lambda oid: book.states.get(int(oid)))
    clock = {"t": 1000.0}                                   # the monotonic clock the cover's confirm reads
    monkeypatch.setattr(live_closes, "time", SimpleNamespace(monotonic=lambda: clock["t"], time=lambda: 0.0))
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: True)
    monkeypatch.setattr("execution.store_orders.short_entries", lambda ids, **kw: {})
    door = Door()
    monkeypatch.setattr(exec_svc, "execute", door.execute)
    audit: list[dict] = []
    monkeypatch.setattr("bot.audit.record", lambda **kw: audit.append(kw) or kw)
    yield SimpleNamespace(book=book, door=door, audit=audit, clock=clock)
    live_closes.reset_for_tests()
    cover_alarm.reset_for_tests()


def _run(now: float) -> list[dict]:
    return asyncio.run(live_closes.pass_once(now=now))


def test_with_live_shorts_off_nova_places_nothing_on_live(live, monkeypatch):
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: False)
    assert _run(_at(15, 56)) == []
    assert live.door.calls == [] and cover_alarm.view()["alarms"] == []


def test_a_live_short_is_left_alone_until_1555(live):
    assert _run(_at(15, 54)) == [] and live.door.calls == []


def test_at_1555_the_stocks_orders_are_cancelled_then_one_market_cover_goes_to_live(live):
    [done] = _run(_at(15, 55))
    cancel, cover = live.door.calls
    assert (cancel.operation, cancel.source, cancel.order_id, cancel.target_venue, cancel.origin) == (
        "cancel", "cancel_working", 41, "live", "day_cover")
    assert (cover.operation, cover.source, cover.intent, cover.side, cover.qty, cover.order_type) == (
        "place", "flatten", "flatten", "BUY", 400, "MKT")
    assert (cover.target_venue, cover.origin, cover.outside_rth, cover.tif) == ("live", "day_cover", False, "DAY")
    assert done["ok"] is True and done["cancelled"] == [41]
    assert cover_alarm.view()["alarms"] == []
    [line] = live.audit
    assert line["action"] == "day_cover" and line["outcome"] == "closed" and "15:55 ET" in line["reason"]

    # The cover is still working at IBKR: never a second one.
    live.book.rows = [{"order_id": done["order_id"], "symbol": "RDYN", "side": "BUY", "order_type": "MKT"}]
    assert _run(_at(15, 55) + 1) == [] and len(live.door.calls) == 2


def test_on_the_paper_gateway_nova_reads_no_live_book_and_raises_the_alarm(live):
    """PR #792 review (P1): the paper Gateway's book is another account -- Nova neither covers nor cancels there,
    and the short it last saw on Live raises the alarm."""
    _run(_at(15, 50))                                     # the Live session reported RDYN short
    live.book.mode, live.book.kind = "paper", "paper"
    live.book.rows = [{"order_id": 51, "symbol": "FADE", "side": "SELL", "order_type": "LMT"}]
    assert _run(_at(15, 56)) == [] and live.door.calls == []
    [alarm] = cover_alarm.view()["alarms"]
    assert alarm["kind"] == "disconnected" and "paper Gateway" in alarm["text"] and "15:50 ET" in alarm["text"]


def test_a_cover_stands_until_ibkrs_position_shows_it(live):
    """PR #792 review (P1): a fill reaches IBKR's orders before its position. A cover gone from the working orders
    while the position still shows the short is never sent again."""
    [done] = _run(_at(15, 55))
    oid = done["order_id"]
    live.book.rows = []                                       # filled: gone from the working orders ...
    live.book.states[oid] = {"status": "Filled", "filled": 400.0, "remaining": 0.0}
    assert _run(_at(15, 55) + 1) == [] and len(live.door.calls) == 2   # ... the position has not caught up
    live.clock["t"] += 5
    assert _run(_at(15, 55) + 6) == [] and len(live.door.calls) == 2
    live.book.positions = {"AAPL": 10.0}                      # the position shows the cover
    assert _run(_at(15, 55) + 7) == [] and cover_alarm.view()["alarms"] == []
    assert live_closes._sent == {}


def test_a_cover_that_closed_with_nothing_filled_is_sent_again(live):
    [done] = _run(_at(15, 55))
    live.book.rows = []
    live.book.states[done["order_id"]] = {"status": "Cancelled", "filled": 0.0, "remaining": 400.0}
    [again] = _run(_at(15, 55) + 1)
    assert again["ok"] is True and [c.operation for c in live.door.calls] == ["cancel", "place", "place"]


def test_a_fill_the_position_never_shows_raises_the_alarm_and_no_second_cover(live):
    from constants_shorts import SHORT_COVER_CONFIRM_SEC

    [done] = _run(_at(15, 55))
    live.book.rows = []
    live.book.states[done["order_id"]] = {"status": "Filled", "filled": 400.0, "remaining": 0.0}
    assert _run(_at(15, 55) + 1) == [] and cover_alarm.view()["alarms"] == []   # filled: the wait starts
    live.clock["t"] += SHORT_COVER_CONFIRM_SEC + 1
    assert _run(_at(15, 56)) == [] and len(live.door.calls) == 2
    [alarm] = cover_alarm.view()["alarms"]
    assert alarm["reason_code"] == "DAY_COVER_UNCONFIRMED" and "no second cover" in alarm["text"]


def test_the_wait_for_the_position_counts_from_the_fill_not_the_send(live):
    """A cover that rested through a halt and then filled raises no alarm while IBKR's position catches up:
    the 15 s count from when it left the working orders."""
    [done] = _run(_at(15, 55))
    live.book.rows = [{"order_id": done["order_id"], "symbol": "RDYN", "side": "BUY", "order_type": "MKT"}]
    live.clock["t"] += 4 * 60                                     # halted: it works four minutes
    assert _run(_at(15, 59)) == [] and len(live.door.calls) == 2
    live.book.rows = []                                           # it fills; the position is a moment behind
    live.book.states[done["order_id"]] = {"status": "Filled", "filled": 400.0, "remaining": 0.0}
    assert _run(_at(15, 59) + 1) == [] and cover_alarm.view()["alarms"] == []
    live.clock["t"] += 1
    live.book.positions = {"AAPL": 10.0}
    assert _run(_at(15, 59) + 2) == [] and cover_alarm.view()["alarms"] == [] and len(live.door.calls) == 2


def test_a_cover_filled_in_parts_stands_until_the_position_shows_every_share(live):
    """PR #793 review (P1): a 400-share cover reads Filled while IBKR's position has applied only its first
    200-share part. The short reading smaller is not the cover confirmed: a second cover for the 200 would leave
    the account 200 long once the rest arrives."""
    from constants_shorts import SHORT_COVER_CONFIRM_SEC

    [done] = _run(_at(15, 55))
    oid = done["order_id"]
    live.book.rows = []
    live.book.states[oid] = {"status": "Filled", "filled": 400.0, "remaining": 0.0}
    live.book.positions = {"RDYN": -200.0, "AAPL": 10.0}       # one part of the fill reached the position
    assert _run(_at(15, 55) + 1) == [] and len(live.door.calls) == 2
    live.clock["t"] += SHORT_COVER_CONFIRM_SEC + 1                # ... and the rest never does: the alarm, no cover
    assert _run(_at(15, 56)) == [] and len(live.door.calls) == 2
    [alarm] = cover_alarm.view()["alarms"]
    assert alarm["reason_code"] == "DAY_COVER_UNCONFIRMED" and "400 filled" in alarm["text"]
    assert "200 short" in alarm["text"]
    live.book.positions = {"AAPL": 10.0}                          # the rest arrives: flat, nothing more is sent
    assert _run(_at(15, 56) + 1) == [] and len(live.door.calls) == 2
    assert cover_alarm.view()["alarms"] == [] and live_closes._sent == {}


def test_a_cover_ibkr_still_works_stands_even_when_its_working_orders_were_read_first(live):
    [done] = _run(_at(15, 55))
    live.book.rows = []                                           # read before IBKR listed its status below
    live.book.states[done["order_id"]] = {"status": "Submitted", "filled": 200.0, "remaining": 200.0}
    live.book.positions = {"RDYN": -200.0, "AAPL": 10.0}
    assert _run(_at(15, 55) + 1) == [] and len(live.door.calls) == 2


def test_a_cover_closed_part_filled_is_followed_by_one_for_the_rest_once_the_position_shows_the_part(live):
    [done] = _run(_at(15, 55))
    live.book.rows = []
    live.book.states[done["order_id"]] = {"status": "Cancelled", "filled": 150.0, "remaining": 250.0}
    assert _run(_at(15, 55) + 1) == [] and len(live.door.calls) == 2     # the position has not shown the 150 yet
    live.book.positions = {"RDYN": -250.0, "AAPL": 10.0}
    [again] = _run(_at(15, 55) + 2)
    assert again["ok"] is True and again["qty"] == 250 and live.door.calls[-1].qty == 250


def test_a_cover_this_session_does_not_know_waits_before_covering_what_is_left(live):
    """A cover placed before a reconnect: IBKR's status of it is unknown, so the short reading smaller does not
    say how much it filled. Nova waits ``SHORT_COVER_CONFIRM_SEC`` for the position to settle, then covers the
    rest."""
    from constants_shorts import SHORT_COVER_CONFIRM_SEC

    _run(_at(15, 55))
    live.book.rows = []                                           # no status in ``states``: unknown to the session
    live.book.positions = {"RDYN": -100.0, "AAPL": 10.0}
    assert _run(_at(15, 55) + 1) == [] and len(live.door.calls) == 2
    live.clock["t"] += SHORT_COVER_CONFIRM_SEC + 1
    [rest] = _run(_at(15, 56))
    assert rest["ok"] is True and rest["qty"] == 100 and cover_alarm.view()["alarms"] == []


def test_a_short_that_survived_the_night_is_covered_at_0930_not_before(live):
    assert _run(_at(9, 0, day=8)) == []
    [alarm] = cover_alarm.view()["alarms"]
    assert alarm["kind"] == "outside_session" and "09:30" in alarm["text"] and live.door.calls == []
    [done] = _run(_at(9, 30, day=8))
    assert done["ok"] is True and cover_alarm.view()["alarms"] == []


def test_after_the_close_nova_sends_nothing_and_raises_the_alarm(live):
    assert _run(_at(16, 5)) == [] and live.door.calls == []
    [alarm] = cover_alarm.view()["alarms"]
    assert (alarm["venue"], alarm["symbol"], alarm["qty"], alarm["kind"]) == ("live", "RDYN", 400.0, "outside_session")


def test_ibkr_down_at_the_cover_raises_the_alarm_from_the_last_short_it_reported(live):
    _run(_at(15, 50))                    # IBKR reported RDYN short
    live.book.ready = False
    assert _run(_at(15, 56)) == [] and live.door.calls == []
    [alarm] = cover_alarm.view()["alarms"]
    assert alarm["kind"] == "disconnected" and alarm["last_seen"] == _at(15, 50)
    assert "15:50 ET" in alarm["text"] and "TWS" in alarm["text"]
    live.book.ready = True
    live.book.positions = {"AAPL": 10.0}  # covered in TWS meanwhile
    _run(_at(15, 57))
    assert cover_alarm.view()["alarms"] == [] and live.door.calls == []


def test_a_cancel_that_fails_leaves_the_short_uncovered_and_raises_the_alarm(live):
    live.door.refuse["cancel"] = "IBKR said no"
    [done] = _run(_at(15, 55))
    assert done["ok"] is False and [c.operation for c in live.door.calls] == ["cancel"]
    [alarm] = cover_alarm.view()["alarms"]
    assert alarm["kind"] == "refused" and "could not cancel" in alarm["text"] and "41" in alarm["text"]
    assert _run(_at(15, 55) + 1) == []        # tried again only after the retry wait
    assert live.audit[-1]["outcome"] == "failed"


def test_an_order_placed_in_tws_blocks_the_cover_and_says_so(live):
    live.book.rows.append({"order_id": 0, "perm_id": 777, "symbol": "RDYN", "side": "BUY", "order_type": "LMT"})
    [done] = _run(_at(15, 55))
    assert done["ok"] is False and [c.operation for c in live.door.calls] == ["cancel"]
    assert "perm id 777" in cover_alarm.view()["alarms"][0]["text"]


def test_a_cover_the_door_refuses_raises_the_alarm_with_its_reason(live):
    live.door.refuse["place"] = "IBKR_ORDERS_ENABLED is false — orders locked"
    [done] = _run(_at(15, 55))
    assert done["ok"] is False
    [alarm] = cover_alarm.view()["alarms"]
    assert alarm["kind"] == "refused" and "IBKR_ORDERS_ENABLED" in alarm["text"] and alarm["reason_code"]


def test_novas_lapsed_live_short_entry_is_cancelled_and_a_longs_exit_never_is(live, monkeypatch):
    live.book.positions = {}
    live.book.rows = [{"order_id": 51, "symbol": "FADE", "side": "SELL", "order_type": "LMT"},    # a short entry
                      {"order_id": 52, "symbol": "AAPL", "side": "SELL", "order_type": "STP"}]     # a long's stop
    placed = _at(10, 0)
    monkeypatch.setattr("execution.store_orders.short_entries",
                        lambda ids, **kw: {51: {"order_id": 51, "created_ts": placed}} if 51 in ids else {})
    assert _run(_at(15, 49)) == []
    [done] = _run(_at(15, 50))
    assert (done["order_id"], done["ok"]) == (51, True)
    [cmd] = live.door.calls
    assert (cmd.operation, cmd.order_id, cmd.target_venue, cmd.origin) == ("cancel", 51, "live", "day_cover")
    assert "New shorts stop at 15:50" in live.audit[-1]["reason"]


def test_the_cutoff_runs_even_with_live_shorts_off(live, monkeypatch):
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: False)
    live.book.positions = {}
    live.book.rows = [{"order_id": 61, "symbol": "FADE", "side": "SELL", "order_type": "LMT"}]
    monkeypatch.setattr("execution.store_orders.short_entries",
                        lambda ids, **kw: {61: {"order_id": 61, "created_ts": _at(10, 0, day=6)}})
    [done] = _run(_at(10, 0))                        # placed yesterday: it never carries into today
    assert done["order_id"] == 61 and "never carries into the next session" in live.audit[-1]["reason"]


# ── the door: Live's cover from a desk that shows Paper ────────────────────────

@pytest.fixture
def door_desk(monkeypatch, tmp_path):
    """The real execution door, the desk on Paper, IBKR ready, and IBKR's book read through ``live_book``."""
    from sim.mode import reset_for_tests as reset_venue, set_venue

    import ibkr.account as account_mod
    import ibkr.orders as orders_mod

    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    inflight.reset_for_tests()
    reset_venue()
    set_venue("paper")
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    session = SimpleNamespace(mode="live", kind="live")      # IBKR's session: the Live Gateway, a live account
    monkeypatch.setattr(client_mod, "account_mode", lambda: session.mode)
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: session.kind)
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    monkeypatch.setattr(safety_mod, "live_trading_confirmed", lambda: True)   # mocked, never set in .env
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    # The desk's own reads say Paper is flat: the check must read IBKR's book, never these.
    monkeypatch.setattr(account_mod, "get_positions", lambda: [])
    book = SimpleNamespace(positions={"RDYN": -400.0}, rows=[])
    monkeypatch.setattr(live_book, "positions", lambda: dict(book.positions))
    monkeypatch.setattr(live_book, "open_rows", lambda: [dict(r) for r in book.rows])
    calls: list[dict] = []

    def place(**kw):
        calls.append(kw)
        return {"ok": True, "order_id": 500 + len(calls), "error": None, "mode": "paper"}

    monkeypatch.setattr(orders_mod, "place_order", place)
    yield SimpleNamespace(book=book, calls=calls, session=session)
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    reset_venue()


def _cover(key: str, qty: float = 400, **kw) -> ExecutionCommand:
    base = dict(operation="place", idempotency_key=key, source="flatten", intent="flatten", symbol="RDYN",
                side="BUY", qty=qty, order_type="MKT", outside_rth=False, tif="DAY", skip_risk=True,
                target_venue="live", origin="day_cover")
    base.update(kw)
    return ExecutionCommand(**base)


def test_the_door_sends_lives_cover_from_a_paper_desk_checked_against_ibkrs_own_short(door_desk):
    receipt = asyncio.run(exec_svc.execute(_cover("dc-1"), wait_ack=False))
    assert receipt.ok is True, receipt.error
    assert receipt.venue == "live"
    [call] = door_desk.calls
    assert call["targeted"] is True and (call["side"], call["qty"], call["order_type"]) == ("BUY", 400, "MKT")


def test_the_door_refuses_a_live_cover_past_ibkrs_short(door_desk):
    door_desk.book.positions = {}
    flat = asyncio.run(exec_svc.execute(_cover("dc-flat"), wait_ack=False))
    assert (flat.ok, flat.reason_code) == (False, "FLATTEN_NOT_A_CLOSE") and "No open RDYN position" in flat.error
    door_desk.book.positions = {"RDYN": -400.0}
    door_desk.book.rows = [{"order_id": 41, "symbol": "RDYN", "side": "BUY", "order_type": "STP",
                            "remaining_qty": 400, "filled_qty": 0}]
    stop_still_working = asyncio.run(exec_svc.execute(_cover("dc-stop"), wait_ack=False))
    assert stop_still_working.reason_code == "FLATTEN_NOT_A_CLOSE" and "already being closed" in stop_still_working.error
    assert door_desk.calls == []


def test_only_lives_day_cover_may_aim_at_live(door_desk):
    margin_call = asyncio.run(exec_svc.execute(_cover("mc-1", origin="margin_call"), wait_ack=False))
    assert margin_call.reason_code == "TARGET_VENUE_REFUSED" and "IBKR liquidates Live itself" in margin_call.error
    no_intent = asyncio.run(exec_svc.execute(_cover("dc-noint", intent=None), wait_ack=False))
    assert no_intent.reason_code == "TARGET_VENUE_REFUSED"
    a_short = asyncio.run(exec_svc.execute(_cover("dc-sell", side="SELL"), wait_ack=False))
    assert a_short.ok is False
    assert door_desk.calls == []


def test_lives_cover_never_goes_to_the_paper_gateway(door_desk):
    """PR #792 review (P1): the legacy paper Gateway connects too, and its account is not the one Live's short is
    in. A day cover aimed at Live goes only while IBKR's session is the Live Gateway on a live account."""
    door_desk.session.mode, door_desk.session.kind = "paper", "paper"
    cover = asyncio.run(exec_svc.execute(_cover("dc-paper-gw"), wait_ack=False))
    assert cover.reason_code == "TARGET_VENUE_REFUSED" and "paper Gateway" in cover.error
    cancel = asyncio.run(exec_svc.execute(ExecutionCommand(
        operation="cancel", idempotency_key="dc-paper-gw-cancel", source="cancel_working", symbol="RDYN",
        order_id=41, target_venue="live", origin="day_cover"), wait_ack=False))
    assert cancel.reason_code == "TARGET_VENUE_REFUSED" and "paper Gateway" in cancel.error
    door_desk.session.mode, door_desk.session.kind = "live", "unknown"   # managedAccounts not in yet
    unnamed = asyncio.run(exec_svc.execute(_cover("dc-unnamed"), wait_ack=False))
    assert unnamed.reason_code == "TARGET_VENUE_REFUSED"
    assert door_desk.calls == []


def test_the_ibkr_adapter_skips_the_desks_practice_guard_only_for_a_targeted_order(monkeypatch):
    import ibkr.orders as orders_mod
    from sim.mode import reset_for_tests as reset_venue, set_venue

    reset_venue()
    set_venue("paper")
    monkeypatch.setattr(client_mod, "is_enabled", lambda: False)    # past the guard, the spend gate refuses
    try:
        guarded = orders_mod.place_order("RDYN", "BUY", 1, "MKT")
        targeted = orders_mod.place_order("RDYN", "BUY", 1, "MKT", targeted=True)
    finally:
        reset_venue()
    assert guarded["ok"] is False and "IBKR_ENABLED" not in str(guarded["error"])     # the desk's guard
    assert targeted["ok"] is False and targeted["error"] == "IBKR_ENABLED is not set"  # the guard was skipped


# ── a Live short entry is never repriced in place ──────────────────────────────

def test_a_live_short_entry_is_never_repriced_and_its_stop_still_moves(monkeypatch):
    from short_sale import door

    entries = {77: {"order_id": 77, "symbol": "FADE", "created_ts": 1.0}}
    monkeypatch.setattr("execution.store_orders.short_entries", lambda ids, **kw: {
        oid: entries[oid] for oid in ids if oid in entries})
    reprice = ExecutionCommand(operation="replace", idempotency_key="r", source="manual", order_id=77,
                               limit_price=4.10)
    detail, code = door.replace_refusal(reprice, "live")
    assert code == "SHORT_REPRICE" and "Cancel it and place it again" in detail
    stop_move = ExecutionCommand(operation="replace", idempotency_key="r2", source="manual", order_id=79,
                                 stop_price=4.30)
    assert door.replace_refusal(stop_move, "live") is None


def test_a_live_reprice_nova_cannot_check_is_refused(monkeypatch):
    from short_sale import door

    def broken(ids, **kw):
        raise RuntimeError("ledger locked")

    monkeypatch.setattr("execution.store_orders.short_entries", broken)
    cmd = ExecutionCommand(operation="replace", idempotency_key="r", source="manual", order_id=5, limit_price=4.0)
    detail, code = door.replace_refusal(cmd, "live")
    assert code == "SHORT_REPRICE" and "ledger locked" not in detail      # the log has the exception (PR #792)


def test_a_live_proof_nova_cannot_read_refuses_in_fixed_words(monkeypatch):
    from short_sale import door

    def broken():
        raise RuntimeError("SECRET-TRACE disk gone")

    monkeypatch.setattr("short_proof.status", broken)
    complete, missing = door.live_proof()
    assert complete is False and "could not be read" in missing and "SECRET-TRACE" not in missing


def test_the_ledger_names_novas_live_short_entries_by_order_id(monkeypatch, tmp_path):
    from execution import store_orders

    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    for key, oid, venue, short in (("a", 70, "live", True), ("b", 71, "live", False), ("c", 72, "paper", True)):
        eid, _new = store.reserve(idempotency_key=key, operation="bracket", source="manual", symbol="FADE",
                                  received_ns=1, payload={"venue": venue, "short_entry": short, "side": "SELL"})
        store.update_stages(eid, order_id=oid)
    assert set(store_orders.short_entries([70, 71, 72])) == {70}
    assert set(store_orders.short_entries([72], venue="paper")) == {72}
    assert store_orders.short_entries([]) == {}
