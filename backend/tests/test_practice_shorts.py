"""Shorts on Paper and Sim (ADR 048 step 2): through the execution door, on the practice ledger.

A short goes out as Live's will -- a bracket with its buy stop -- and the door runs the one short
check on every venue (``short_sale.check``): the hours, halts, borrow, SSR, margin and the 25%
cushion, with no Live key on a practice venue. The ledger holds it short; SSR holds a short's fill
at or under the bid; Nova covers what is left at 15:55 and closes what the margin no longer
carries, through the door, on the venue that holds the position whatever the desk shows. Every
position says its side and the price at which IBKR would liquidate it.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import ibkr.shortability as short_mod
from constants_practice import PRACTICE_STARTING_CASH
from execution import inflight, service, store, telemetry
from execution.models import ExecutionCommand
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from short_sale import check, closes, door, halts, hours, positions, ssr, ssr_fill
from short_sale import facts as short_facts
from short_sale import routes as short_routes
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

ET = ZoneInfo("America/New_York")
SYMBOL = "FADE"


def _at(hour: int, minute: int, second: int = 0) -> float:
    return datetime(2026, 10, 7, hour, minute, second, tzinfo=ET).timestamp()


class Market:
    """The live feed as Paper sees it: FADE at 4.00 (3.99 x 4.01), its clock set by the test."""

    def __init__(self, now: float) -> None:
        self.now = now
        self.last, self.bid, self.ask = 4.00, 3.99, 4.01

    def reference(self, symbol: str) -> Reference:
        if symbol != SYMBOL:
            return Reference(None, live=True)
        return Reference(self.last, self.bid, self.ask, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYMBOL else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def bid_at(self, symbol: str, ts: float) -> float | None:
        """The bid a print at ``ts`` met: the bid the test set before handing the print over."""
        return self.bid if symbol == SYMBOL else None

    def now_ts(self) -> float:
        return self.now

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


def _borrow(shares: float = 50_000) -> dict:
    return short_mod.enrich_ibkr_listing(
        {"connected": True, "qualified": True, "shortable_shares": shares, "error": None},
        fetched_at=time.time(),     # a live borrow read's age is wall-clock seconds
    )


@pytest.fixture
def paper(monkeypatch, short_market_open):
    reset_venue()
    reset_for_tests()
    service.reset_for_tests()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    short_mod.reset_for_tests()
    closes.reset_for_tests()
    store.init_db()
    market = Market(short_market_open)
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: market)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    short_mod.remember_for_tests(SYMBOL, _borrow())
    audit: list[dict] = []
    monkeypatch.setattr("bot.audit.record", lambda **kw: audit.append(kw) or kw)
    yield SimpleNamespace(broker=for_venue("paper"), market=market, now=short_market_open, audit=audit)
    closes.reset_for_tests()
    service.reset_for_tests()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    short_mod.reset_for_tests()
    reset_for_tests()
    reset_venue()


def _short(key: str, qty: float = 500, entry: float = 4.00, stop: float | None = 4.20,
           target: float | None = 3.60, **kw) -> ExecutionCommand:
    if stop is None:   # a plain limit: no buy stop
        return ExecutionCommand(operation="place", idempotency_key=key, source="manual", symbol=SYMBOL,
                                side="SELL", qty=qty, order_type="LMT", limit_price=entry, short_entry=True,
                                skip_risk=True, **kw)
    return ExecutionCommand(operation="bracket", idempotency_key=key, source="manual", symbol=SYMBOL, side="SELL",
                            qty=qty, order_type="LMT", limit_price=entry, entry_price=entry, stop_price=stop,
                            target_price=target, short_entry=True, skip_risk=True, **kw)


def _send(cmd: ExecutionCommand):
    return asyncio.run(service.execute(cmd, wait_ack=False))


def _held(broker) -> float:
    return float(broker.ledger.held_qty(SYMBOL))


# ── the door: a short on Paper ─────────────────────────────────────────────────

def test_a_short_goes_out_as_a_bracket_and_the_ledger_holds_it_short(paper) -> None:
    paper.market.bid = 4.00                        # the 4.00 short is marketable: it fills at the bid
    receipt = _send(_short("open"))

    assert receipt.ok is True, receipt.error
    assert receipt.broker_status == "Filled" and _held(paper.broker) == -500
    legs = {r["leg_role"]: r for r in paper.broker.working_orders()}
    assert {(role, r["side"], r["status"]) for role, r in legs.items()} == {
        ("target", "BUY", "Submitted"), ("stop", "BUY", "Submitted"),
    }
    [row] = positions.decorate(paper.broker.positions(), "paper")
    assert row["position_side"] == "short"
    # 5,000 - 500 (p - 4) = 500 x 5.00 a share (the $5-16.67 tier) -> p = 9.00, fees aside.
    assert row["liquidation_price"] == pytest.approx(9.0, abs=0.05)
    assert row["liquidation_source"] == "published rules"


def test_paper_needs_no_live_key_and_live_still_refuses_without_it(paper) -> None:
    assert _safety.short_enabled() is False        # IBKR_SHORT_ENABLED is never set by a test
    assert _send(_short("paper-ok")).ok is True
    detail, code = door.refusal(_short("live-no"), venue="live")
    assert code == "SHORT_DISABLED" and "IBKR_SHORT_ENABLED" in detail


@pytest.mark.parametrize(("case", "code"), [
    ("no_stop", "SHORT_NEEDS_STOP"),
    ("too_early", "SHORT_HOURS"),
    ("too_late", "SHORT_HOURS"),
    ("halted", "SHORT_HALTED"),
    ("cooling_off", "SHORT_HALT_COOLOFF"),
    ("halt_unknown", "SHORT_HALT_UNKNOWN"),
    ("ssr_at_bid", "SHORT_SSR_AT_BID"),
    ("ssr_no_bid", "SHORT_SSR_NO_BID"),
    ("borrow_small", "SHORT_BORROW_TOO_SMALL"),
    ("small_equity", "SHORT_EQUITY"),
    ("too_big", "SHORT_MARGIN"),
    ("no_cushion", "SHORT_CUSHION"),
])
def test_every_rule_refuses_with_its_own_code_on_paper(paper, monkeypatch, case: str, code: str) -> None:
    cmd = _short(f"refused-{case}")
    if case == "no_stop":
        cmd = _short("refused-no-stop", stop=None)
    elif case in ("too_early", "too_late"):
        clock = _at(9, 34) if case == "too_early" else _at(15, 51)
        monkeypatch.setattr(short_facts, "venue_now", lambda venue: clock)
    elif case in ("halted", "cooling_off", "halt_unknown"):
        state = {"halted": "halted", "cooling_off": "cooloff", "halt_unknown": "unknown"}[case]
        monkeypatch.setattr(halts, "live", lambda symbol, now=None: halts.HaltRead(state, f"{symbol}: {state}."))
    elif case in ("ssr_at_bid", "ssr_no_bid"):
        monkeypatch.setattr(ssr, "live", lambda symbol, now=None: ssr.SsrRead("on", "SSR is on today.", "today"))
        cmd = _short("refused-ssr", entry=3.99, stop=4.20)
        if case == "ssr_no_bid":
            paper.market.bid = None
    elif case == "borrow_small":
        short_mod.remember_for_tests(SYMBOL, _borrow(shares=12_000))   # under 10,000 IBKR's estimate reads thin
        cmd = _short("refused-borrow", qty=12_500)    # the borrow is judged before the margin
    elif case == "small_equity":
        paper.broker.reset(1_500)
    elif case == "too_big":
        cmd = _short("refused-big", qty=1_500)       # $5.00 a share x 1,500 = 7,500 of 5,000
    elif case == "no_cushion":
        cmd = _short("refused-cushion", qty=850)     # fits, but IBKR would liquidate under 5.00
    events = len(paper.broker.ledger.events)

    receipt = _send(cmd)

    assert (receipt.ok, receipt.reason_code) == (False, code), receipt.error
    assert len(paper.broker.ledger.events) == events and _held(paper.broker) == 0


def test_a_short_is_refused_while_the_stock_is_held_long(paper) -> None:
    paper.broker.place(SYMBOL, "BUY", 100, "MKT")
    receipt = _send(_short("while-long"))
    assert (receipt.ok, receipt.reason_code) == (False, "SHORT_WHILE_LONG")
    assert _held(paper.broker) == 100


def test_a_short_counts_the_shorts_already_held_against_the_borrow(paper) -> None:
    paper.market.bid = 4.00
    short_mod.remember_for_tests(SYMBOL, _borrow(shares=12_000))
    assert _send(_short("first", qty=500)).ok is True
    receipt = _send(_short("second", qty=11_800))
    assert (receipt.ok, receipt.reason_code) == (False, "SHORT_BORROW_TOO_SMALL")
    assert "500 already short" in receipt.error


def test_the_tickets_short_with_its_buy_stop_alone_rests_as_two_orders(paper) -> None:
    """The ticket's Short sends its required buy stop and, unless set, no cover target (step 3)."""
    from routes.trading_execution import OrderRequest, _manual_order_command

    req = OrderRequest(symbol=SYMBOL, side="SELL", qty=500, order_type="LMT", limit_price=4.50,
                       short_entry=True, stop_loss_price=4.80)
    receipt = _send(_manual_order_command(req, "ticket-short", None, 0))
    assert receipt.ok is True, receipt.error
    legs = {r["leg_role"]: r for r in paper.broker.working_orders()}
    assert set(legs) == {"parent", "stop"} and receipt.target_order_id is None
    assert (legs["parent"]["side"], legs["parent"]["short_entry"]) == ("SELL", True)
    assert (legs["stop"]["side"], legs["stop"]["status"]) == ("BUY", "PreSubmitted")


# ── SSR: a short fills only above the bid ─────────────────────────────────────

def test_adding_above_the_market_counts_the_short_held_from_its_mark(paper) -> None:
    """PR #786 review: 100 short at $10, adding 250 resting at $20, on $5,000 -- IBKR liquidates near 24.18."""
    paper.market.last, paper.market.bid, paper.market.ask = 10.00, 10.00, 10.01   # a buyer at 10: it fills
    held = _send(_short("held-at-10", qty=100, entry=10.00, stop=10.50, target=9.00))
    assert held.ok is True and _held(paper.broker) == -100, held.error
    more = _send(_short("add-at-20", qty=250, entry=20.00, stop=21.00, target=18.00))
    # Counted as if the 100 sold at $20 too, the add passed (liquidation near 26.37, over 25).
    assert (more.ok, more.reason_code) == (False, "SHORT_CUSHION")
    assert "counted from its mark 10.00" in more.error and _held(paper.broker) == -100


def test_under_ssr_a_short_rests_until_it_can_fill_above_the_bid(paper, monkeypatch) -> None:
    monkeypatch.setattr(ssr, "live", lambda symbol, now=None: ssr.SsrRead("on", "SSR is on today.", "today"))
    monkeypatch.setattr(ssr_fill, "effective_on", lambda *a, **k: True)
    receipt = _send(_short("ssr", entry=4.01, stop=4.30))          # over the 3.99 bid: the door lets it go
    assert receipt.ok is True and receipt.broker_status == "Submitted"

    paper.market.bid = 4.01                                        # the bid rose to the short's price
    paper.market.now += 5
    assert paper.broker.try_fill_working(SYMBOL, [(paper.market.now, 4.02)]) == []
    assert _held(paper.broker) == 0 and receipt.parent_order_id in {
        int(r["order_id"]) for r in paper.broker.working_orders()}

    paper.market.bid = 4.00                                        # under it again: a buyer lifts the short
    paper.market.now += 5
    filled = paper.broker.try_fill_working(SYMBOL, [(paper.market.now, 4.01)])
    assert [(r["order_id"], r["avg_fill_price"]) for r in filled] == [(receipt.parent_order_id, 4.01)]
    assert _held(paper.broker) == -500


def test_under_ssr_a_print_fills_against_the_bid_that_stood_then(paper, monkeypatch) -> None:
    """PR #786 review: a jump or a late read never judges an earlier print by the bid now."""
    monkeypatch.setattr(ssr_fill, "effective_on", lambda *a, **k: True)
    receipt = _send(_short("ssr-then", entry=4.05, stop=4.30))
    assert receipt.ok is True and _held(paper.broker) == 0
    at_print: dict[float, float] = {}
    paper.market.bid_at = lambda symbol, ts: at_print.get(ts)
    first, second = paper.market.now + 5, paper.market.now + 10
    at_print.update({first: 4.05, second: 4.04})      # the short's price was the bid at the first print
    paper.market.bid = 3.50                          # ... and the bid now says nothing about either
    assert paper.broker.try_fill_working(SYMBOL, [(first, 4.05)]) == []
    filled = paper.broker.try_fill_working(SYMBOL, [(second, 4.05)])
    assert [r["order_id"] for r in filled] == [receipt.parent_order_id] and _held(paper.broker) == -500
    # A print whose bid Nova never saw proves nothing: the short rests.
    again = _send(_short("ssr-unseen", qty=100, entry=4.05, stop=4.30))
    assert paper.broker.try_fill_working(SYMBOL, [(paper.market.now + 15, 4.06)]) == []
    assert again.parent_order_id in {int(r["order_id"]) for r in paper.broker.working_orders()}


def test_under_ssr_a_marketable_short_rests_instead_of_filling_at_the_bid(paper, monkeypatch) -> None:
    monkeypatch.setattr(ssr_fill, "effective_on", lambda *a, **k: True)
    raw = paper.broker.place(SYMBOL, "SELL", 100, "LMT", limit_price=3.99, short_entry=True)
    assert (raw["ok"], raw["broker_status"]) == (True, "Submitted") and _held(paper.broker) == 0
    # A cover is never held by SSR.
    assert ssr_fill.allows("paper", {"symbol": SYMBOL, "side": "BUY", "short_entry": False}, 3.0,
                           paper.market, paper.now) is True


# ── Nova's closes: the day cover and the margin call ──────────────────────────

def _open_short(paper, qty: float = 500) -> int:
    paper.market.bid = 4.00
    receipt = _send(_short(f"open-{qty}", qty=qty))
    assert receipt.ok is True and _held(paper.broker) == -qty, receipt.error
    return int(receipt.parent_order_id)


def test_the_day_cover_waits_for_1555_then_covers_through_the_door(paper) -> None:
    parent = _open_short(paper)
    paper.market.now = _at(15, 54, 59)
    assert asyncio.run(closes.day_cover(paper.broker)) == []

    set_venue("sim")      # the desk moved: Paper's short is still covered, on Paper
    paper.market.now = _at(15, 55)
    [done] = asyncio.run(closes.day_cover(paper.broker))

    assert (done["ok"], done["venue"], done["side"], done["qty"]) == (True, "paper", "BUY", 500)
    assert sorted(done["cancelled"]) == [parent + 1, parent + 2] and done["cancel_failed"] == []
    assert _held(paper.broker) == 0 and paper.broker.working_orders() == []
    row = {int(r["order_id"]): r for r in paper.broker.closed_orders()}[done["order_id"]]
    assert (row["order_origin"], row["order_source"], row["effect"], row["position_side"]) == (
        "day_cover", "flatten", "closes", "short")
    [line] = [a for a in paper.audit if a["action"] == "day_cover"]
    assert line["outcome"] == "closed" and "15:55 ET" in line["reason"]
    assert asyncio.run(closes.day_cover(paper.broker)) == []     # nothing left to cover


def test_a_short_entry_still_resting_at_1550_is_cancelled_before_it_fills(paper) -> None:
    """PR #786 review: a short the door let go before 15:50 never opens after it."""
    receipt = _send(_short("rest-past", entry=4.50, stop=4.80, target=4.00))   # over the market: it rests
    assert receipt.ok is True and _held(paper.broker) == 0
    paper.market.now = _at(15, 49, 59)
    assert asyncio.run(closes.entry_cutoff(paper.broker)) == []
    set_venue("sim")     # the desk moved: Paper's entry is still cancelled, on Paper
    paper.market.now = _at(15, 50)
    [done] = asyncio.run(closes.entry_cutoff(paper.broker))
    assert (done["ok"], done["venue"], done["order_id"]) == (True, "paper", receipt.parent_order_id)
    assert paper.broker.working_orders() == []        # its waiting stop and target went with it
    row = {int(r["order_id"]): r for r in paper.broker.closed_orders()}[receipt.parent_order_id]
    assert row["status"] == "Cancelled" and row["order_origin"] in (None, "day_cover")
    [line] = [a for a in paper.audit if a["action"] == "day_cover"]
    assert line["outcome"] == "cancelled" and "New shorts stop at 15:50 ET" in line["reason"]
    assert asyncio.run(closes.entry_cutoff(paper.broker)) == []


def test_a_gtc_short_entry_is_cancelled_before_the_next_open(paper) -> None:
    receipt = _send(_short("rest-overnight", entry=4.50, stop=4.80, target=4.00, tif="GTC"))
    assert receipt.ok is True
    paper.market.now = _at(9, 0) + 86_400            # the next morning, before 09:35
    [done] = asyncio.run(closes.entry_cutoff(paper.broker))
    assert done["ok"] is True and paper.broker.working_orders() == [] and _held(paper.broker) == 0


def test_a_gtc_short_entry_from_an_earlier_session_is_cancelled_inside_todays_hours(paper) -> None:
    """PR #787 review: Nova was closed over the 15:50 cutoff and came back after the next 09:35. The entry's
    borrow, SSR, halt and margin checks were the day before's: it never rests or fills into a new session."""
    receipt = _send(_short("rest-closed-over", entry=4.50, stop=4.80, target=4.00, tif="GTC"))
    assert receipt.ok is True
    paper.market.now = _at(10, 0) + 86_400           # Thursday 10:00, inside its short hours
    assert hours.entry_refusal(paper.market.now) is None
    [done] = asyncio.run(closes.entry_cutoff(paper.broker))
    assert (done["ok"], done["order_id"]) == (True, receipt.parent_order_id)
    assert paper.broker.working_orders() == [] and _held(paper.broker) == 0
    [line] = [a for a in paper.audit if a["action"] == "day_cover"]
    assert line["outcome"] == "cancelled" and "placed on 2026-10-07" in line["reason"]
    assert asyncio.run(closes.entry_cutoff(paper.broker)) == []


def test_a_print_the_next_day_never_fills_an_earlier_sessions_short_entry(paper) -> None:
    """Before the runner's first pass, the matcher's next-day prints cancel the entry instead of filling it."""
    receipt = _send(_short("rest-gtc-fill", qty=100, entry=4.50, stop=4.80, target=4.00, tif="GTC"))
    assert receipt.ok is True and _held(paper.broker) == 0
    paper.market.now = _at(9, 41) + 86_400
    assert paper.broker.try_fill_working(SYMBOL, [(_at(9, 40) + 86_400, 4.55)]) == []
    assert _held(paper.broker) == 0 and paper.broker.working_orders() == []
    [event] = [e for e in paper.broker.ledger.events
               if e.get("type") == "cancelled" and e.get("order_id") == receipt.parent_order_id]
    assert event["code"] == "SHORT_HOURS" and "placed on 2026-10-07" in event["reason"]


def test_a_replace_never_carries_a_short_entry_into_a_new_session(paper) -> None:
    """A replace re-dates the order's ``placed_ts`` (no fill on prints before it), never the session it was
    checked in: a short entry repriced the next morning still lapses."""
    receipt = _send(_short("rest-replaced", qty=100, entry=4.50, stop=4.80, target=4.00, tif="GTC"))
    assert receipt.ok is True
    parent = int(receipt.parent_order_id)
    paper.market.now = _at(9, 40) + 86_400
    assert paper.broker.replace(parent, limit_price=4.45)["ok"] is True
    row = paper.broker.ledger.working_row(parent)
    assert row["placed_ts"] == paper.market.now and row["entered_ts"] == paper.now
    paper.market.now = _at(9, 42) + 86_400
    assert paper.broker.try_fill_working(SYMBOL, [(_at(9, 41) + 86_400, 4.50)]) == []
    assert _held(paper.broker) == 0 and paper.broker.working_orders() == []


def test_a_short_entry_repriced_the_same_day_still_fills(paper) -> None:
    receipt = _send(_short("rest-same-day", qty=100, entry=4.50, stop=4.80, target=4.00))
    assert receipt.ok is True
    paper.market.now = paper.now + 60
    assert paper.broker.replace(int(receipt.parent_order_id), limit_price=4.40)["ok"] is True
    filled = paper.broker.try_fill_working(SYMBOL, [(paper.now + 61, 4.41)])
    assert [int(r["order_id"]) for r in filled] == [receipt.parent_order_id] and _held(paper.broker) == -100


def test_a_print_past_1550_never_fills_a_resting_short_entry(paper) -> None:
    """A Sim jump past 15:50 fills on the prints it crossed before the runner's cutoff pass: the fill refuses."""
    early = _send(_short("rest-early", qty=100, entry=4.50, stop=4.80, target=4.00))
    late = _send(_short("rest-late", qty=100, entry=4.60, stop=4.90, target=4.10))
    assert early.ok is True and late.ok is True and _held(paper.broker) == 0
    paper.market.now = _at(15, 52)                     # the playhead jumped; no cutoff pass has run
    filled = paper.broker.try_fill_working(SYMBOL, [(_at(15, 49, 30), 4.55), (_at(15, 50, 30), 4.65)])
    # The 15:49:30 print was inside the hours: it fills the 4.50 short. The later one cancels the 4.60.
    assert [int(r["order_id"]) for r in filled] == [early.parent_order_id] and _held(paper.broker) == -100
    [event] = [e for e in paper.broker.ledger.events
               if e.get("type") == "cancelled" and e.get("order_id") == late.parent_order_id]
    assert event["code"] == "SHORT_HOURS" and "New shorts stop at 15:50 ET" in event["reason"]
    late_legs = {late.target_order_id, late.stop_order_id}
    assert late_legs.isdisjoint({int(r["order_id"]) for r in paper.broker.working_orders()})


def test_the_cutoff_leaves_a_longs_orders_and_a_shorts_exits_alone(paper) -> None:
    long_entry = paper.broker.place(SYMBOL, "BUY", 10, "LMT", limit_price=3.50)     # rests under the market
    paper.market.now = _at(15, 51)
    assert asyncio.run(closes.entry_cutoff(paper.broker)) == []
    assert [int(r["order_id"]) for r in paper.broker.working_orders()] == [long_entry["order_id"]]
    paper.broker.cancel(long_entry["order_id"])
    paper.market.now = paper.now
    _open_short(paper)            # filled: its stop and target rest as exits, never short entries
    paper.market.now = _at(15, 51)
    assert asyncio.run(closes.entry_cutoff(paper.broker)) == []
    assert sorted(r["effect"] for r in paper.broker.working_orders()) == ["closes", "closes"]


def test_a_short_found_before_the_open_is_covered_too(paper) -> None:
    _open_short(paper)
    paper.market.now = _at(9, 0)                   # e.g. a short Nova was closed over
    [done] = asyncio.run(closes.day_cover(paper.broker))
    assert done["ok"] is True and _held(paper.broker) == 0


def test_the_day_cover_leaves_longs_alone(paper) -> None:
    paper.broker.place(SYMBOL, "BUY", 100, "MKT")
    paper.market.now = _at(15, 56)
    assert asyncio.run(closes.day_cover(paper.broker)) == []
    assert _held(paper.broker) == 100


def test_a_refused_close_waits_before_it_is_tried_again(paper, monkeypatch) -> None:
    _open_short(paper)
    paper.market.now = _at(15, 56)
    real = service.execute

    async def refuse_the_close(cmd, **kw):
        if cmd.operation == "place":
            return SimpleNamespace(ok=False, order_id=None, error="refused for the test", reason_code="TEST")
        return await real(cmd, **kw)

    monkeypatch.setattr(service, "execute", refuse_the_close)
    [first] = asyncio.run(closes.day_cover(paper.broker))
    assert (first["ok"], first["reason_code"]) == (False, "TEST")
    assert [a["outcome"] for a in paper.audit if a["action"] == "day_cover"] == ["failed"]
    assert asyncio.run(closes.day_cover(paper.broker)) == []        # not on every pass
    assert _held(paper.broker) == -500

    closes._retry_at[("paper", SYMBOL, "day_cover")] = 0.0          # SHORT_CLOSE_RETRY_SEC later
    monkeypatch.setattr(service, "execute", real)
    [again] = asyncio.run(closes.day_cover(paper.broker))
    assert again["ok"] is True and _held(paper.broker) == 0
    assert closes._retry_at == {}


def test_the_margin_call_closes_the_short_when_equity_falls_under_maintenance(paper) -> None:
    raw = paper.broker.place(SYMBOL, "SELL", 500, "LMT", limit_price=3.99, short_entry=True)
    assert raw["broker_status"] == "Filled"
    assert asyncio.run(closes.margin_call(paper.broker)) == []        # 5,000 of equity over 2,000

    # 5,000 - 500 x (9.50 - 3.99) = 2,245 of equity under 2,500 of maintenance: the call reads the
    # venue's last price itself, nothing else marked the position.
    paper.market.last, paper.market.bid, paper.market.ask = 9.50, 9.49, 9.51
    [done] = asyncio.run(closes.margin_call(paper.broker))

    assert (done["ok"], done["side"], done["qty"]) == (True, "BUY", 500)
    assert _held(paper.broker) == 0
    row = {int(r["order_id"]): r for r in paper.broker.closed_orders()}[done["order_id"]]
    assert row["order_origin"] == "margin_call"
    [line] = [a for a in paper.audit if a["action"] == "margin_call"]
    assert "maintenance requirement" in line["reason"]


def test_only_the_closes_name_a_venue_other_than_the_desks(paper, monkeypatch) -> None:
    from execution.venue_door import target_refusal

    def cmd(**kw) -> ExecutionCommand:
        base = dict(operation="place", idempotency_key="t", source="flatten", symbol=SYMBOL, side="BUY", qty=1,
                    order_type="MKT", target_venue="paper", origin="day_cover")
        base.update(kw)
        return ExecutionCommand(**base)

    assert target_refusal(cmd()) is None
    assert target_refusal(cmd(origin="margin_call")) is None
    assert target_refusal(cmd(operation="cancel", source="cancel_working", order_id=1)) is None
    assert target_refusal(cmd(source="manual")) is not None           # a manual order goes to the desk's venue
    assert target_refusal(cmd(origin="ticket_flatten")) is not None
    assert target_refusal(cmd(side="SELL", short_entry=True)) is not None
    monkeypatch.setattr("execution.venue_door.ibkr_connected", lambda: True)
    assert "Paper and Sim only" in target_refusal(cmd(target_venue="live"))   # Live's cover is step 6


# ── positions ──────────────────────────────────────────────────────────────────

def test_a_long_the_account_pays_for_has_no_liquidation_price(paper) -> None:
    paper.broker.place(SYMBOL, "BUY", 100, "MKT")
    [row] = positions.decorate(paper.broker.positions(), "paper")
    assert (row["position_side"], row["liquidation_price"]) == ("long", None)


def test_a_practice_account_starts_at_5000_with_four_times_its_buying_power(paper) -> None:
    paper.broker.reset()
    summary = paper.broker.account_summary()
    assert PRACTICE_STARTING_CASH == 5_000
    assert (summary["NetLiquidation"], summary["BuyingPower"]) == (5_000, 20_000)
    assert (summary["MaintMarginReq"], summary["ExcessLiquidity"]) == (0, 5_000)


# ── the read-only check and a replay's facts ───────────────────────────────────

def test_the_short_check_route_lists_every_rule_and_places_nothing(paper) -> None:
    answer = asyncio.run(short_routes.get_short_check(SYMBOL, qty=500, price=4.00, stop=4.20, target=None))
    assert (answer["ok"], answer["venue"], answer["first"]) == (True, "paper", None)
    assert [r["id"] for r in answer["rules"]] == [
        "order", "not_long", "account", "hours", "halt", "borrow", "ssr", "margin", "cushion"]
    assert answer["facts"]["hours"]["cover"] == _at(15, 55)
    no_stop = asyncio.run(short_routes.get_short_check(SYMBOL, qty=500, price=4.00, stop=None, target=None))
    assert no_stop["ok"] is False and no_stop["first"]["code"] == "SHORT_NEEDS_STOP"
    assert paper.broker.ledger.events == []


def test_a_replay_shorts_only_on_borrow_recorded_then(monkeypatch) -> None:
    from short_sale import borrow_log

    at = _at(10, 30)
    monkeypatch.setattr(borrow_log, "at", lambda symbol, ts: {"ts": ts - 30, "shares": 12_000, "state": "ok"})
    snap, why = short_facts._recorded_borrow(SYMBOL, at)
    assert why is None and (snap["shortable_shares"], snap["source"]) == (12_000, "recorded")

    monkeypatch.setattr(borrow_log, "at", lambda symbol, ts: {"ts": ts - 7_200, "shares": 12_000, "state": "ok"})
    snap, why = short_facts._recorded_borrow(SYMBOL, at)
    assert snap is None and "08:30" in why
    monkeypatch.setattr(borrow_log, "at", lambda symbol, ts: None)
    snap, why = short_facts._recorded_borrow(SYMBOL, at)
    assert snap is None and "no borrow recorded" in why

    replay = short_facts.Facts(venue="sim", symbol=SYMBOL, now=at, replay=True, borrow=None, borrow_why=why,
                               whatif=None, ssr=ssr.SsrRead("unknown", "SSR unknown."),
                               halt=halts.HaltRead("clear", "trading"), bid=3.99, ask=4.01, last=4.0)
    account = check.Account(summary={"connected": True, "NetLiquidation": 5_000, "ExcessLiquidity": 5_000,
                                     "account_class": "margin"}, positions=[], held_long=0.0, held_short=0.0)
    order = check.Order(symbol=SYMBOL, qty=100, entry=4.00, stop=4.20)
    assert check.first_refusal(check.rules(order, replay, account, live_key=None))[1] == "SHORT_NO_RECORDED_BORROW"


def test_one_venues_failed_pass_never_stops_the_others(monkeypatch) -> None:
    brokers = {"paper": SimpleNamespace(venue="paper"), "sim": SimpleNamespace(venue="sim")}

    async def day_cover(broker):
        if broker.venue == "paper":
            raise RuntimeError("paper's ledger is unreadable")
        return [{"venue": broker.venue}]

    async def margin_call(broker):
        return []

    async def entry_cutoff(broker):
        return []

    monkeypatch.setattr("practice.broker.loaded", lambda venue: brokers.get(venue))
    monkeypatch.setattr(closes, "entry_cutoff", entry_cutoff)
    monkeypatch.setattr(closes, "day_cover", day_cover)
    monkeypatch.setattr(closes, "margin_call", margin_call)
    assert asyncio.run(closes.pass_once()) == [{"venue": "sim"}]
    brokers.pop("sim")
    assert asyncio.run(closes.pass_once()) == []      # an unloaded venue is never loaded to look
