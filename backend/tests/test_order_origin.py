"""Who sent an order (operator report 2026-10-01: "I don't remember selling it").

The bot trip sold 100 ACN on Paper and the Orders table showed it as one more market sell: the
row said ``order_source: flatten``, which the ticket's Flatten, the header's KILL, both loss
breakers and the bot's own exit all send. Every sender now stamps its ``origin``, the execution
record and the practice row keep it, and the Live closed rows join it from the ledger.
"""
from __future__ import annotations

import typing
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from constants_nova_os import EXECUTION_ORIGINS
from constants_practice import PRACTICE_NO_LIVE_PRINT_CODE, PRACTICE_NO_LIVE_PRINT_REASON
from execution.models import ExecutionCommand, Origin
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

NOW = 1_700_000_000.0


def test_the_origin_vocabulary_is_one_list() -> None:
    assert typing.get_args(Origin) == EXECUTION_ORIGINS


def test_the_execution_record_keeps_the_origin() -> None:
    from execution.record_payload import build_reserve_payload

    cmd = ExecutionCommand(operation="place", idempotency_key="k", source="flatten", symbol="ACN",
                           side="SELL", qty=100, origin="bot_trip")
    payload = build_reserve_payload(cmd, requested_qty=100, sent_qty=100, requested_price=None,
                                    measurement={}, forced_one_share=False)
    assert payload["origin"] == "bot_trip"
    plain = ExecutionCommand(operation="place", idempotency_key="k2", source="manual")
    assert build_reserve_payload(plain, requested_qty=None, sent_qty=None, requested_price=None,
                                 measurement={}, forced_one_share=False)["origin"] is None


# -- the practice row carries it -----------------------------------------------------------
class _Live:
    def __init__(self) -> None:
        self.ref = Reference(10.0, 9.98, 10.02, live=True)

    def reference(self, symbol: str) -> Reference:
        return self.ref if symbol == "IMCC" else Reference(None, live=True)

    def admission(self, symbol: str):
        if symbol == "IMCC":
            return True, "OK", None
        return False, PRACTICE_NO_LIVE_PRINT_REASON, PRACTICE_NO_LIVE_PRINT_CODE

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return NOW


@pytest.fixture
def paper(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr(practice_broker, "LiveReference", _Live)
    yield SimpleNamespace(broker=for_venue("paper"))
    reset_for_tests()


def test_a_practice_order_row_says_who_sent_it(paper) -> None:
    paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5, source="bot", origin="auto_entry")
    paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.4)
    rows = {row["limit_price"]: row for row in paper.broker.working_orders()}
    assert (rows[9.5]["order_source"], rows[9.5]["order_origin"]) == ("bot", "auto_entry")
    assert (rows[9.4]["order_source"], rows[9.4]["order_origin"]) == ("manual", None)   # your ticket


def test_every_leg_of_a_practice_bracket_carries_the_origin(paper) -> None:
    raw = paper.broker.place_bracket("IMCC", "BUY", 10, 9.5, 11.0, 9.0, source="manual", origin="approve")
    assert raw["ok"] is True
    legs = paper.broker.working_orders()
    assert len(legs) == 3 and {row["order_origin"] for row in legs} == {"approve"}


@pytest.mark.asyncio
async def test_the_practice_send_passes_the_commands_origin(monkeypatch) -> None:
    from sim import execution as sim_execution

    seen: dict = {}

    class _Broker:
        venue = "paper"
        reference = SimpleNamespace(admission=lambda _sym: (True, "OK", None))

        def place(self, **kw):
            seen.update(kw)
            return {"ok": False, "error": "stop here", "reason_code": "TEST"}

    monkeypatch.setattr(sim_execution, "_receipt_from_raw", AsyncMock(return_value="receipt"))
    monkeypatch.setattr("execution.store.update_stages", lambda *a, **k: None)
    cmd = ExecutionCommand(operation="place", idempotency_key="k", source="flatten", symbol="ACN",
                           side="SELL", qty=100, origin="bot_trip")
    from execution.models import StageTimings

    await sim_execution.send_practice_broker(cmd, "e1", StageTimings(received_ns=0), broker=_Broker(),
                                             reject=lambda *a: None)
    assert seen["origin"] == "bot_trip" and seen["source"] == "flatten"


# -- the Live rows join it from the ledger -------------------------------------------------
def test_a_live_closed_row_takes_who_sent_it_from_the_ledger() -> None:
    from execution.closed_blotter import _merge_ib_ledger, _row_from_ledger

    led = {"id": "e1", "source": "flatten", "symbol": "ACN", "order_id": 7, "status": "filled",
           "payload": {"side": "SELL", "qty": 100, "origin": "all_stop"}}
    assert {k: _row_from_ledger(led)[k] for k in ("order_source", "order_origin")} == {
        "order_source": "flatten", "order_origin": "all_stop"}
    merged = _merge_ib_ledger({"order_id": 7, "symbol": "ACN", "qty": 100, "filled_qty": 100}, led)
    assert (merged["order_source"], merged["order_origin"]) == ("flatten", "all_stop")
    old = {**led, "payload": {"side": "SELL", "qty": 100}}             # recorded before origins
    assert _row_from_ledger(old)["order_origin"] is None


# -- each sender stamps its own ------------------------------------------------------------
class _Receipt:
    def legacy_place_dict(self):
        return {"ok": True, "order_id": 68, "error": None}


@pytest.mark.asyncio
async def test_a_flatten_close_carries_its_callers_origin(monkeypatch) -> None:
    from bot import flatten as flatten_mod
    from execution import flatten_exit as fe

    captured: dict = {}

    async def fake_execute(cmd, wait_ack=False):
        captured["cmd"] = cmd
        return _Receipt()

    monkeypatch.setattr(fe, "flatten_needs_extended_hours", lambda now=None: False)
    monkeypatch.setattr(fe, "resolve_flatten_marks", lambda _symbol: (10.0, 10.1, 10.05))
    monkeypatch.setattr("execution.service.execute", fake_execute)
    await flatten_mod._place_close("ACN", 100, "SELL", origin="bot_trip")
    assert (captured["cmd"].source, captured["cmd"].origin) == ("flatten", "bot_trip")


def test_closes_sold_names_each_position_the_flatten_closed() -> None:
    from bot.flatten import closes_sold

    result = {"ok": False, "results": [
        {"symbol": "ACN", "qty": 100.0, "side": "SELL", "close": {"ok": True, "order_id": 68, "error": None}},
        {"symbol": "NXL", "qty": 5.0, "side": "SELL", "close": {"ok": False, "order_id": None, "error": "no mark"}},
    ]}
    assert closes_sold(result) == [
        {"symbol": "ACN", "side": "SELL", "qty": 100.0, "ok": True, "order_id": 68, "error": None},
        {"symbol": "NXL", "side": "SELL", "qty": 5.0, "ok": False, "order_id": None, "error": "no mark"},
    ]
    assert closes_sold({"ok": True, "results": []}) == []


@pytest.fixture
def paper_desk():
    reset_venue()
    set_venue("paper", persist=False)
    yield
    reset_venue()


@pytest.mark.parametrize(("pnl", "action", "origin"), [(-60.0, "breaker_soft", "bot_trip"),
                                                       (-250.0, "breaker_hard", "all_stop")])
@pytest.mark.asyncio
async def test_a_breaker_flattens_as_itself_and_lists_what_it_sold(paper_desk, monkeypatch, pnl, action, origin):
    from bot.audit import list_entries
    from bot.breakers import poll_once

    asked: list = []

    async def flatten(*, origin=None):
        asked.append(origin)
        return {"ok": True, "attempt": 1, "results": [
            {"symbol": "ACN", "qty": 100.0, "side": "SELL", "close": {"ok": True, "order_id": 68, "error": None}},
        ]}

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", flatten)
    await poll_once(pnl=pnl)
    assert asked == [origin]
    line = next(e for e in list_entries(limit=20) if e["action"] == action)
    assert line["inputs"]["closes"] == [
        {"symbol": "ACN", "side": "SELL", "qty": 100.0, "ok": True, "order_id": 68, "error": None}]
    assert line["inputs"]["flatten_error"] is None and line["venue"] == "paper"


def test_the_emergency_kill_flatten_reads_as_kill() -> None:
    from fastapi.testclient import TestClient

    from main import app

    fake = AsyncMock(return_value={"ok": True, "attempt": 1, "results": [], "cancels": []})
    with patch("bot.flatten.flatten_account_with_retry", fake):
        assert TestClient(app).post("/api/ibkr/flatten-account").status_code == 200
    fake.assert_awaited_once_with(origin="emergency_kill")


def test_the_tickets_flatten_reads_as_yours() -> None:
    from routes.trading_execution import OrderRequest, _manual_order_command

    def cmd(**kw):
        req = OrderRequest(symbol="ACN", side="SELL", qty=100, order_type="MKT", **kw)
        return _manual_order_command(req, "k", None, 0)

    assert (cmd(intent="flatten").source, cmd(intent="flatten").origin) == ("flatten", "ticket_flatten")
    assert (cmd().source, cmd().origin) == ("manual", None)


@pytest.mark.asyncio
async def test_auto_entry_and_approve_say_so(monkeypatch) -> None:
    from stock_mode import orders

    sent: list = []

    async def fake_execute(cmd, wait_ack=False):
        sent.append(cmd)
        return None

    monkeypatch.setattr(orders, "execute", fake_execute)
    monkeypatch.setattr(orders, "_outside_rth", lambda: False)
    trade = {"kind": "auto_entry", "venue": "paper", "symbol": "ACN", "attempt": 1, "qty": 10,
             "entry": 224.41, "stop": 221.88, "target": 229.47, "setup_type": "flat_top_breakout"}
    await orders.place_entry(trade)
    await orders.send_bracket({**trade, "kind": "approve"})
    assert [(c.source, c.origin) for c in sent] == [("bot", "auto_entry"), ("manual", "approve")]


@pytest.mark.asyncio
async def test_novas_bot_says_so_on_its_entry_exit_and_last_resort(monkeypatch) -> None:
    from bot.first_pullback import orders

    sent: list = []

    async def fake_execute(cmd, wait_ack=False):
        sent.append(cmd)
        return None

    monkeypatch.setattr(orders, "execute", fake_execute)
    monkeypatch.setattr(orders, "_outside_rth", lambda: False)
    trade = {"setup_id": "s1", "venue": "paper", "symbol": "ACN", "qty": 10, "entry_planned": 224.41,
             "target1": 229.47, "stop": 221.88, "setup_type": "first_pullback"}
    await orders.place_entry(trade)
    await orders.replace_stop(trade, 5, 222.5)
    await orders._place(trade, "close:1", side="SELL", qty=10, order_type="LMT", limit_price=224.0)
    assert {c.origin for c in sent} == {"bot"}
    placed: dict = {}

    async def fake_close(symbol, qty, side, *, origin=None):
        placed["origin"] = origin
        return {"ok": True}

    monkeypatch.setattr("bot.flatten.place_close", fake_close)
    await orders.protective_close(trade, 10)
    assert placed["origin"] == "bot"
