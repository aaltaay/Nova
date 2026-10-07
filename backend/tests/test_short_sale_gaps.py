"""ADR 048 step 1: the eight gaps the short-selling design found, each closed and pinned.

1. a short entry is checked against margin and the 25% cushion;
2. never a short while the account holds the stock long;
3. a cover is never refused by the day lock or by buying power;
4. the door reads borrow from the cache, outside its lock, and never asks IBKR;
5. a short entry is held in flight, so two cannot over-short;
6. Freeze all orders keeps the stops that protect a position (``test_kill_switch_keeps_stops.py``);
7. Fill now never re-sends a short as a plain SELL (frontend, ``planFillWorkingOrder.test.ts``);
8. Paper and Sim never fill a cover past flat (``test_practice_overcover.py``).

Each short goes out as ADR 048 step 2 requires: a bracket with its buy stop, inside the short hours,
with halts and SSR pinned clear (``short_market_open``).
"""
from __future__ import annotations

import asyncio
import time

import pytest

import execution.inflight as inflight
import execution.service as exec_svc
import execution.store as store
import execution.telemetry as telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
import ibkr.shortability as short_mod
import kill_switch
import strategy.risk as risk_mod
from bot.buy_lock import buy_refusal
from bot.persist import load_session, save_session
from execution import validate
from execution.models import ExecutionCommand
from execution.venue_door import commit_position
from short_sale import margin

SYMBOL = "RDYN"


def _borrow(shares: float = 30_000, age: float = 1.0) -> dict:
    return short_mod.enrich_ibkr_listing(
        {"connected": True, "qualified": True, "shortable_shares": shares, "error": None},
        fetched_at=time.time() - age,
    )


def _short(key: str = "short-1", qty: float = 416, limit: float = 5.77, **kw) -> ExecutionCommand:
    """A short as the door takes it: a bracket with its buy stop (ADR 048 1.6)."""
    base = dict(operation="bracket", idempotency_key=key, source="manual", symbol=SYMBOL, side="SELL",
                qty=qty, order_type="LMT", limit_price=limit, entry_price=limit, stop_price=round(limit + 0.12, 2),
                target_price=round(limit - min(0.24, limit / 4), 2), short_entry=True, skip_risk=True)
    base.update(kw)
    return ExecutionCommand(**base)


def _short_bracket(key: str = "short-b", qty: float = 416) -> ExecutionCommand:
    return ExecutionCommand(operation="bracket", idempotency_key=key, source="manual", symbol=SYMBOL,
                            side="SELL", qty=qty, order_type="LMT", limit_price=5.77, entry_price=5.77,
                            stop_price=5.89, target_price=5.53, short_entry=True, skip_risk=True)


def _cover(key: str = "cover-1", qty: float = 100) -> ExecutionCommand:
    return ExecutionCommand(operation="place", idempotency_key=key, source="manual", symbol=SYMBOL, side="BUY",
                            qty=qty, order_type="LMT", limit_price=5.50, skip_risk=True)


def _summary(equity: float = 5_000.0, excess: float | None = 5_000.0, **kw) -> dict:
    row = {"connected": True, "pending": False, "NetLiquidation": equity, "BuyingPower": 20_000.0,
           "account_class": "margin"}
    if excess is not None:
        row["ExcessLiquidity"] = excess
    row.update(kw)
    return row


@pytest.fixture
def live(monkeypatch, tmp_path, short_market_open):
    """A Live desk on IBKR with shorts enabled (the key is mocked: no agent sets it)."""
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    store.init_db()
    telemetry.reset_for_tests()
    inflight.reset_for_tests()
    short_mod.reset_for_tests()
    risk_mod.reset_day()
    kill_switch._tripped = False
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_QTY_CAP", "100000")     # the Live test cap would cut every size to 1
    state = {"summary": _summary(), "positions": []}
    monkeypatch.setattr(account_mod, "get_account_summary", lambda: state["summary"])
    monkeypatch.setattr(account_mod, "get_positions", lambda: state["positions"])
    # The door must never ask IBKR for borrow (gap 4): any synchronous read fails the test.
    monkeypatch.setattr(short_mod, "fetch_shortability",
                        lambda symbol: pytest.fail(f"the door asked IBKR for {symbol}'s borrow"))
    refreshed: list[str] = []
    monkeypatch.setattr(short_mod, "request_refresh", lambda symbol: refreshed.append(symbol) or True)
    state["refreshed"] = refreshed
    yield state
    inflight.reset_for_tests()
    short_mod.reset_for_tests()
    telemetry.reset_for_tests()
    kill_switch._tripped = False


def _spy_place(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def place(**kw):
        calls.append(kw)
        return {"ok": True, "order_id": 100 + len(calls), "error": None, "mode": "paper"}

    def bracket(**kw):
        calls.append(kw)
        base = 100 + 3 * len(calls)
        return {"ok": True, "order_id": base, "parent_order_id": base, "target_order_id": base + 1,
                "stop_order_id": base + 2, "error": None, "mode": "paper"}

    monkeypatch.setattr(orders_mod, "place_order", place)
    monkeypatch.setattr(orders_mod, "place_bracket_order", bracket)
    return calls


def _check(cmd: ExecutionCommand, borrow: dict | None = None) -> tuple[bool, str, str | None]:
    return validate.check_account_and_position(cmd, borrow=borrow, venue="live")


# ---------------------------------------------------------------- gap 1: margin and the cushion
def test_published_margin_tiers_and_the_cushion_cap():
    assert margin.short_maint_per_share(2.00) == 2.50
    assert margin.short_maint_per_share(3.00) == 3.00
    assert margin.short_maint_per_share(10.00) == 5.00
    assert margin.short_maint_per_share(20.00) == pytest.approx(6.00)
    # $5,000 on a stock under $5 caps a short at about $3,300 (the operator's own number).
    for entry in (3.00, 4.00):
        cap_qty = int(5_000 / (entry * 1.5))
        ok = margin.cushion(equity=5_000, other_maint=0, qty=cap_qty, entry=entry)
        over = margin.cushion(equity=5_000, other_maint=0, qty=cap_qty + 5, entry=entry)
        assert ok["ok"] is True and over["ok"] is False
        assert cap_qty * entry == pytest.approx(3_333, abs=10)


def test_liquidation_price_is_where_equity_meets_maintenance():
    liq = margin.short_liquidation_price(equity=5_000, other_maint=0, qty=800, mark=4.00)
    # 5000 - 800 (p - 4) = 800 * m(p): under $5 m(p) = p, so 8200 = 1600 p -> 5.125; past $5 m = 5:
    # 5000 - 800 (p - 4) = 4000 -> p = 5.25.
    assert liq == pytest.approx(5.25, abs=1e-4)
    # A long of 1,000 at $4 on $2,000 of equity: 2000 + 1000 (p - 4) = 0.25 * 1000 * p -> p = 2.6667.
    long = margin.long_liquidation_price(equity=2_000, other_maint=0, qty=1_000, mark=4.00)
    assert long == pytest.approx(8 / 3, abs=1e-9)
    assert margin.long_liquidation_price(equity=4_000, other_maint=0, qty=1_000, mark=4.00) is None


def test_a_short_too_big_for_the_cushion_is_refused(live):
    live["summary"] = _summary(equity=5_000, excess=5_000)
    ok, detail, code = _check(_short(qty=1_000, limit=4.00), _borrow())
    assert (ok, code) == (False, "SHORT_CUSHION")
    assert "25%" in detail and "published rules" in detail
    ok, _detail, code = _check(_short(qty=800, limit=4.00), _borrow())
    assert (ok, code) == (True, None)


def test_a_short_that_does_not_fit_is_refused_margin(live):
    live["summary"] = _summary(equity=5_000, excess=500)      # 4,500 already needed by other positions
    ok, detail, code = _check(_short(qty=400, limit=4.00), _borrow())
    assert (ok, code) == (False, "SHORT_MARGIN")
    assert "$500.00 left" in detail


def test_unknown_margin_refuses(live):
    live["summary"] = _summary(excess=None)
    live["positions"] = [{"symbol": "GAPX", "qty": 100, "avg_cost": 1.9, "market_value": None}]
    ok, _detail, code = _check(_short(), _borrow())
    assert (ok, code) == (False, "SHORT_MARGIN_UNKNOWN")
    live["summary"] = {"connected": True, "pending": True}
    assert _check(_short(), _borrow())[2] == "SHORT_MARGIN_UNKNOWN"


def test_cash_account_and_small_equity_refuse(live):
    live["summary"] = _summary(account_class="cash")
    assert _check(_short(), _borrow())[2] == "SHORT_NOT_MARGIN"
    live["summary"] = _summary(equity=1_500, excess=1_500)
    ok, detail, code = _check(_short(qty=10), _borrow())
    assert (ok, code) == (False, "SHORT_EQUITY") and "$2,000.00" in detail


def test_a_market_short_is_refused(live):
    market = ExecutionCommand(operation="place", idempotency_key="mkt", source="manual", symbol=SYMBOL,
                              side="SELL", qty=10, order_type="MKT", short_entry=True, skip_risk=True)
    ok, _detail, code = _check(market, _borrow())
    assert (ok, code) == (False, "SHORT_NEEDS_LIMIT")


def test_a_short_without_its_buy_stop_is_refused(live):
    """ADR 048 1.6: a plain limit short carries no stop -- no stop price, no short."""
    plain = ExecutionCommand(operation="place", idempotency_key="no-stop", source="manual", symbol=SYMBOL,
                             side="SELL", qty=10, order_type="LMT", limit_price=5.77, short_entry=True,
                             skip_risk=True)
    ok, detail, code = _check(plain, _borrow())
    assert (ok, code) == (False, "SHORT_NEEDS_STOP") and "buy stop" in detail


# ---------------------------------------------------------------- gap 2: never short while long
def test_a_short_is_refused_while_the_account_holds_the_stock_long(live):
    live["positions"] = [{"symbol": SYMBOL, "qty": 200, "avg_cost": 5.1, "market_value": None}]
    ok, detail, code = _check(_short(), _borrow())
    assert (ok, code) == (False, "SHORT_WHILE_LONG")
    assert "200" in detail and "never flips" in detail


# ---------------------------------------------------------------- gap 3: covers are never locked
def test_a_cover_is_never_locked_by_the_day_lock():
    assert buy_refusal("BUY", "manual", "live", covers=True) is None


def test_a_cover_skips_buying_power_but_never_buys_past_the_short(live):
    live["positions"] = [{"symbol": SYMBOL, "qty": -416, "avg_cost": 5.77, "market_value": None}]
    live["summary"] = _summary(BuyingPower=0.0)
    assert _check(_cover(qty=416)) == (True, "OK", None)
    ok, _detail, code = _check(_cover(qty=417))
    assert (ok, code) == (False, "OVERCOVER")
    # A BUY when flat is an entry, and still meets buying power.
    live["positions"] = []
    assert _check(_cover(qty=10))[2] == "BUYING_POWER"


def test_the_door_lets_a_cover_through_the_all_stop(live, monkeypatch):
    live["positions"] = [{"symbol": SYMBOL, "qty": -416, "avg_cost": 5.77, "market_value": None}]
    row = load_session()
    row["hard_lock_until_date"] = "2099-01-01"
    save_session(row)
    try:
        calls = _spy_place(monkeypatch)
        cover = asyncio.run(exec_svc.execute(_cover("door-cover", qty=416), wait_ack=False))
        assert cover.ok is True, cover.error
        live["positions"] = []
        buy = asyncio.run(exec_svc.execute(_cover("door-buy", qty=10), wait_ack=False))
        assert (buy.ok, buy.reason_code) == (False, "BOT_DAY_LOCK")
        assert len(calls) == 1
    finally:
        row = load_session()
        row["hard_lock_until_date"] = None
        save_session(row)


# ---------------------------------------------------------------- gap 4: borrow from the cache
def test_the_door_reads_borrow_from_the_cache_and_asks_in_the_background(live, monkeypatch):
    calls = _spy_place(monkeypatch)
    missing = asyncio.run(exec_svc.execute(_short("no-cache", qty=10), wait_ack=False))
    assert (missing.ok, missing.reason_code) == (False, "SHORT_STALE_BORROW")
    assert "asked IBKR" in missing.error and live["refreshed"] == [SYMBOL]

    short_mod.remember_for_tests(SYMBOL, _borrow(age=120.0))
    stale = asyncio.run(exec_svc.execute(_short("stale-cache", qty=10), wait_ack=False))
    assert (stale.ok, stale.reason_code) == (False, "SHORT_STALE_BORROW")
    assert "120 s old" in stale.error and live["refreshed"] == [SYMBOL, SYMBOL]

    short_mod.remember_for_tests(SYMBOL, _borrow(age=1.0))
    fresh = asyncio.run(exec_svc.execute(_short("fresh-cache", qty=10), wait_ack=False))
    assert fresh.ok is True, fresh.error
    assert len(calls) == 1 and calls[0]["side"] == "SELL"


def test_an_open_tab_rereads_borrow_before_it_goes_stale():
    snap = _borrow()
    assert short_mod.refresh_due(snap, 19.0) is False
    assert short_mod.refresh_due(snap, 20.0) is True       # well under the 60 s TTL


# ---------------------------------------------------------------- gap 5: shorts in flight
def test_short_entries_are_held_in_flight_as_short():
    inflight.reset_for_tests()
    try:
        commit_position(_short("held-1", qty=300), "exec-1", SYMBOL, "live")
        commit_position(_short_bracket("held-2", qty=200), "exec-2", SYMBOL, "live")
        assert inflight.committed_qty(SYMBOL, inflight.SHORT, "live") == 500
        assert inflight.committed_qty(SYMBOL, "SELL", "live") == 0     # never shrinks a closing sell
        assert {row.price for row in inflight.commitments(inflight.SHORT, "live")} == {5.77}
    finally:
        inflight.reset_for_tests()


def test_two_shorts_cannot_over_short_the_borrow(live, monkeypatch):
    calls = _spy_place(monkeypatch)
    short_mod.remember_for_tests(SYMBOL, _borrow(shares=12_000))
    live["summary"] = _summary(equity=50_000, excess=50_000)
    first = asyncio.run(exec_svc.execute(_short("borrow-1", qty=8_000, limit=0.20), wait_ack=False))
    assert first.ok is True, first.error
    second = asyncio.run(exec_svc.execute(_short("borrow-2", qty=8_000, limit=0.20), wait_ack=False))
    assert (second.ok, second.reason_code) == (False, "SHORT_BORROW_TOO_SMALL")
    assert "8,000 on the way" in second.error
    assert len(calls) == 1


def test_shorts_in_flight_count_toward_the_margin(live, monkeypatch):
    _spy_place(monkeypatch)
    short_mod.remember_for_tests(SYMBOL, _borrow())
    short_mod.remember_for_tests("FADE", _borrow())
    first = asyncio.run(exec_svc.execute(_short("margin-1", qty=600, limit=4.00), wait_ack=False))
    assert first.ok is True, first.error
    second = asyncio.run(exec_svc.execute(
        _short("margin-2", qty=600, limit=4.00, symbol="FADE"), wait_ack=False))
    assert second.ok is False and second.reason_code in ("SHORT_MARGIN", "SHORT_CUSHION")


def test_the_live_key_still_refuses_first(live, monkeypatch):
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: False)
    short_mod.remember_for_tests(SYMBOL, _borrow())
    assert _check(_short(), _borrow())[2] == "SHORT_DISABLED"
