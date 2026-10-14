"""A Time & Sales missing trades locks orders, Paper fills as Live would, and Nova asks IBKR's data back.

ADR 045 amendment 2026-10-14 (#722). GENK on Paper: the AllLast line printed nothing from 09:25:11 to
09:28:25 while Level 1 traded 2.83 down to 2.31; a buy limit 2.76 placed at 09:25:19 passed the gate, sat
unfilled for three minutes, filled at once on the first print back and the bot trip sold it 0.8 s later.
"""
from __future__ import annotations

import time
from datetime import datetime
from types import SimpleNamespace

import pytest

import instance_identity
from constants_market_view import FEED_STALE, TAPE_STALE
from main import app
from market_view import gate, versions
from practice.clock import ET
# Imported before any fixture patches ``sim.mode``: this route binds ``is_replay_desk`` at import, and a
# first import inside a test would keep the patched one for every later test (the Sim venue's own tests).
from routes import trading_tape_ws

T0 = datetime(2026, 10, 14, 9, 25, 11, tzinfo=ET).timestamp()  # GENK's last print


@pytest.fixture(autouse=True)
def _live_feed(monkeypatch):
    versions.reset_for_tests()
    from ibkr import feed_pulse
    from perf import stall_watch
    import sim.mode

    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda now=None: [])
    monkeypatch.setattr(stall_watch, "stalled_ms", lambda name: 0.0)
    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: False)
    yield
    versions.reset_for_tests()


def _line(monkeypatch, *, subscribed=True, last=T0, exchange=T0, opened=T0 - 300, l1=T0 + 8, halted=False):
    from ibkr import halt_status, tape_silence, tape_stream
    import ibkr.tape_recording as tape_recording

    monkeypatch.setattr(tape_stream, "is_subscribed", lambda sym: subscribed)
    monkeypatch.setattr(tape_recording, "producer_status", lambda sym: {
        "last_print_ts": last, "last_print_exchange_ts": exchange, "line_since": opened})
    monkeypatch.setattr(tape_silence, "l1_trade_at", lambda sym: l1)
    monkeypatch.setattr(halt_status, "halted_now", lambda syms, now=None: {s: halted for s in syms})


# ── missing trades, no wait ───────────────────────────────────────────────


def test_level_1_trades_the_tape_never_printed_are_missing_trades(monkeypatch):
    from ibkr import tape_silence

    _line(monkeypatch)
    out = tape_silence.missed_trades("genk", now=T0 + 8)
    assert out is not None and out["since"] == T0 and out["l1_trade_ts"] == T0 + 8
    assert out["text"].startswith("GENK's Time & Sales is missing trades: its last print came at 09:25:11 ET")
    assert "Level 1 shows trades up to 09:25:19 ET" in out["text"]


@pytest.mark.parametrize("kwargs", [
    {"l1": T0 + 1},            # Level 1 inside the lead: the tape keeps up
    {"l1": None},              # no Level 1 trade clock: nothing proven
    {"halted": True},          # a halt prints nothing
    {"subscribed": False},     # no line, no tape to judge
])
def test_a_tape_that_keeps_up_halts_or_has_no_line_is_not_missing_trades(monkeypatch, kwargs):
    from ibkr import tape_silence

    _line(monkeypatch, **kwargs)
    assert tape_silence.missed_trades("GENK", now=T0 + 8) is None


def test_a_line_that_never_printed_counts_from_its_opening(monkeypatch):
    from ibkr import tape_silence

    _line(monkeypatch, last=None, exchange=None, opened=T0, l1=T0 + 4)
    out = tape_silence.missed_trades("SCNI", now=T0 + 5)
    assert out is not None and "it has printed nothing since it opened" in out["text"]


# ── the gate: one judge ───────────────────────────────────────────────────


def _cmd(symbol="GENK"):
    act = time.time() * 1000.0
    view = {"schema_version": 1, "symbol": symbol, "action_wall_ms": act,
            "instance": instance_identity.INSTANCE_ID, "book": None, "quote": None, "desk": None}
    return SimpleNamespace(operation="place", source="manual", symbol=symbol, view=view,
                           client_timing={"action_wall_ms": act}, backend_ingress_wall_ns=int((act + 20) * 1e6))


def test_the_genk_order_is_refused_while_its_tape_misses_trades(monkeypatch):
    now = time.time()
    _line(monkeypatch, last=now - 8, exchange=now - 8, l1=now)
    check = gate.check(_cmd())
    assert check.refused and check.code == TAPE_STALE
    assert "GENK's Time & Sales is missing trades" in check.text
    assert check.text.endswith("Nothing was sent. Flatten and cancels still work.")
    assert check.record()["tape_missing_since"] is not None


def test_the_desk_sees_the_doors_own_words_before_the_click(monkeypatch):
    now = time.time()
    _line(monkeypatch, last=now - 8, exchange=now - 8, l1=now)
    lock = gate.desk_lock("GENK", now=now)
    assert lock is not None and lock["code"] == TAPE_STALE
    assert lock["text"].endswith("New orders on it wait until its prints are back. Flatten and cancels still work.")
    assert "Nothing was sent" not in lock["text"]


def test_the_api_answers_with_the_same_lock(monkeypatch):
    from fastapi.testclient import TestClient

    now = time.time()
    _line(monkeypatch, last=now - 8, exchange=now - 8, l1=now)
    body = TestClient(app).get("/api/market-view/gate", params={"symbol": "genk"}).json()
    assert body["symbol"] == "GENK" and body["locked"] is True and body["code"] == TAPE_STALE
    _line(monkeypatch, last=now, exchange=now, l1=now)
    body = TestClient(app).get("/api/market-view/gate", params={"symbol": "GENK"}).json()
    assert body == {**body, "locked": False, "code": None, "text": None}


def test_a_feed_gap_still_comes_first_and_a_replay_desk_is_never_held(monkeypatch):
    from ibkr import feed_pulse
    import sim.mode

    now = time.time()
    _line(monkeypatch, last=now - 8, exchange=now - 8, l1=now)
    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda t=None: [{"start": now - 4.0, "end": None}])
    assert gate.desk_lock("GENK", now=now)["code"] == FEED_STALE
    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: True)
    assert gate.desk_lock("GENK", now=now) is None


def test_flatten_and_cancels_are_never_held_by_the_tape(monkeypatch):
    now = time.time()
    _line(monkeypatch, last=now - 8, exchange=now - 8, l1=now)
    for source, operation in (("flatten", "place"), ("kill", "place"), ("manual", "cancel"), ("bot", "place")):
        cmd = _cmd()
        cmd.source, cmd.operation = source, operation
        assert gate.check(cmd).verdict == "exempt"


# ── Nova asks IB Gateway for its data back ────────────────────────────────


@pytest.fixture
def recovery(monkeypatch):
    from ibkr import gateway_api_heal, tape_recovery
    import ibkr.tape_recording as tape_recording

    tape_recovery.reset_for_tests()
    sent: list[str] = []
    rows: list[dict] = []
    answer = {"error": None}

    class NowThread:
        def __init__(self, target, args=(), **_kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(tape_recovery.threading, "Thread", NowThread)
    monkeypatch.setattr(tape_recovery.time, "sleep", lambda s: None)
    monkeypatch.setattr(tape_recovery, "_connected", lambda: True)
    monkeypatch.setattr(gateway_api_heal, "send_ibc_command", lambda cmd: sent.append(cmd) or answer["error"])
    monkeypatch.setattr(tape_recovery, "_persist", lambda phase, attempt: rows.append({"phase": phase, **attempt}))
    monkeypatch.setattr(tape_recording, "producer_status",
                        lambda sym: {"last_print_ts": T0 + 200 if sym == "GENK" else T0})
    monkeypatch.delenv(tape_recovery.ENV_SWITCH, raising=False)
    yield tape_recovery, sent, rows, answer
    tape_recovery.reset_for_tests()


def test_a_dead_line_asks_the_gateway_to_reconnect_its_data_once_and_measures_it(recovery):
    tape_recovery, sent, rows, _answer = recovery
    reading = {"since": T0, "pipeline": ["BEZ", "MXCT"], "history_unanswered_since": T0}
    attempt = tape_recovery.line_dead("GENK", reading, now=T0 + 10)
    assert attempt is not None and attempt["lines"] == ["BEZ", "GENK", "MXCT"]
    assert sent == ["RECONNECTDATA"]
    done = tape_recovery.attempts()[-1]
    assert done["sent"] is True and done["back"] == ["GENK"] and done["still_dead"] == ["BEZ", "MXCT"]
    assert [r["phase"] for r in rows] == ["sent", "verified"]
    assert "prints were back on GENK" in tape_recovery.words_since(T0)
    assert tape_recovery.line_dead("BEZ", reading, now=T0 + 60) is None          # inside the cooldown
    assert sent == ["RECONNECTDATA"]


def test_a_failed_ask_says_why(recovery):
    tape_recovery, _sent, rows, answer = recovery
    answer["error"] = "IBC's command server did not answer on 127.0.0.1:7462"
    tape_recovery.line_dead("GENK", {"since": T0, "pipeline": []}, now=T0 + 10)
    assert tape_recovery.attempts()[-1]["sent"] is False and [r["phase"] for r in rows] == ["sent"]
    assert "could not ask IB Gateway" in tape_recovery.words_since(T0)


def test_no_ask_without_a_gateway_or_when_turned_off(recovery, monkeypatch):
    tape_recovery, sent, _rows, _answer = recovery
    monkeypatch.setenv(tape_recovery.ENV_SWITCH, "0")
    assert tape_recovery.line_dead("GENK", {"since": T0}, now=T0 + 10) is None
    monkeypatch.delenv(tape_recovery.ENV_SWITCH)
    monkeypatch.setattr(tape_recovery, "_connected", lambda: False)
    assert tape_recovery.line_dead("GENK", {"since": T0}, now=T0 + 10) is None
    assert sent == []


def test_a_dead_reading_hands_the_line_over_and_carries_the_words(monkeypatch):
    from ibkr import tape_recovery, tape_silence

    asked: list[str] = []
    monkeypatch.setattr(tape_recovery, "line_dead", lambda sym, out, now=None: asked.append(sym))
    monkeypatch.setattr(tape_recovery, "words_since", lambda since: "Nova asked IB Gateway to reconnect.")
    out = tape_silence._with_recovery("GENK", {"state": "dead", "since": T0, "text": "Down."}, T0 + 10)
    assert asked == ["GENK"] and out["text"] == "Down. Nova asked IB Gateway to reconnect."
    out = tape_silence._with_recovery("XLU", {"state": "silent", "since": T0, "text": "Silent."}, T0 + 10)
    assert asked == ["GENK"]                                   # only a dead line asks


def test_ibkrs_connectivity_messages_are_kept_for_the_report(monkeypatch):
    from ibkr import farm_notices
    from perf import recorder

    rows: list[dict] = []
    monkeypatch.setattr(recorder, "persist", rows.append)
    farm_notices.record_connectivity(1100, "connectivity_lost", " Connectivity ... lost. ", now=T0)
    assert rows[0]["kind"] == "ib_notice" and rows[0]["code"] == 1100
    assert rows[0]["notice"] == "connectivity_lost" and rows[0]["farm"] is None
    assert rows[0]["message"] == "Connectivity ... lost."


# ── Paper fills as Live would ─────────────────────────────────────────────


class _Live:
    def __init__(self) -> None:
        self.now = T0 + 8
        self.l1: tuple[float, float] | None = None

    def reference(self, symbol):
        from sim.fill_model import Reference

        return Reference(2.76, 2.79, 2.77, live=True)

    def admission(self, symbol):
        return True, "OK", None

    def prints_between(self, symbol, after_ts, through_ts):
        return []

    def now_ts(self):
        return self.now

    def l1_trade_while_tape_missing(self, symbol):
        return self.l1


@pytest.fixture
def paper(monkeypatch):
    from practice import matcher, tape_hold
    from practice.broker import PracticeBroker
    from practice.ledger import Ledger

    async def reconcile(wanted):
        return {}

    monkeypatch.setattr(tape_hold, "reconcile", reconcile)
    monkeypatch.setattr(matcher, "_note_silence", lambda symbol: None)
    matcher.reset_for_tests()
    ref = _Live()
    broker = PracticeBroker(ref, Ledger(100_000, created_ts=T0), "NOVA-PAPER", venue="paper")
    yield matcher, broker, ref
    matcher.reset_for_tests()


@pytest.mark.asyncio
async def test_the_genk_buy_fills_when_level_1_trades_through_it_not_three_minutes_later(paper):
    matcher, broker, ref = paper
    assert broker.place("GENK", "BUY", 1000, "LMT", limit_price=2.76)["broker_status"] == "Submitted"
    ref.now = T0 + 12
    ref.l1 = (T0 + 11, 2.7592)            # 09:25:22: IBKR's Level 1 trades through the limit
    filled = await matcher.pass_once(broker)
    assert [(r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(2.76, "l1_last")]
    assert broker.positions()[0]["qty"] == 1000


@pytest.mark.asyncio
async def test_a_level_1_trade_is_used_once_and_never_one_from_before_the_order(paper):
    matcher, broker, ref = paper
    broker.place("GENK", "BUY", 1000, "LMT", limit_price=2.50)
    ref.l1 = (T0 + 7, 2.40)               # stamped before the order rested
    assert await matcher.pass_once(broker) == []
    ref.l1 = (T0 + 11, 2.60)              # above the limit
    assert await matcher.pass_once(broker) == []
    assert await matcher.pass_once(broker) == []
    ref.l1 = (T0 + 12, 2.45)
    assert len(await matcher.pass_once(broker)) == 1


@pytest.mark.asyncio
async def test_while_the_tape_keeps_up_only_prints_fill(paper):
    matcher, broker, ref = paper
    broker.place("GENK", "BUY", 1000, "LMT", limit_price=2.76)
    ref.l1 = None
    assert await matcher.pass_once(broker) == []
    assert broker.working_orders()


# ── the trip names the order it sold ──────────────────────────────────────


def test_the_trip_names_the_order_that_opened_what_it_sold(monkeypatch):
    from bot import flatten
    from execution import store

    rows = [
        {"order_id": 256, "symbol": "GENK", "operation": "place", "status": "filled", "source": "flatten",
         "mode": "paper", "created_ts": T0 + 196, "updated_ts": T0 + 196, "payload": {"side": "SELL", "qty": 1000}},
        {"order_id": 900, "symbol": "GENK", "operation": "place", "status": "filled", "source": "manual",
         "mode": "live", "created_ts": T0 + 100, "updated_ts": T0 + 101, "payload": {"side": "BUY", "qty": 1}},
        {"order_id": 255, "symbol": "GENK", "operation": "place", "status": "filled", "source": "manual",
         "mode": "paper", "created_ts": T0 + 8, "updated_ts": T0 + 195,
         "payload": {"side": "BUY", "sent_qty": 1000, "order_type": "LMT", "requested_price": 2.76}},
    ]
    monkeypatch.setattr(store, "list_recent", lambda limit=100: rows)
    result = {"results": [{"symbol": "GENK", "qty": 1000, "side": "SELL", "close": {"ok": True, "order_id": 256}}]}
    [close] = flatten.closes_sold(result, venue="paper")
    assert close["order_id"] == 256
    assert close["opened_by"] == {"order_id": 255, "source": "manual", "side": "BUY", "qty": 1000,
                                  "order_type": "LMT", "price": 2.76, "placed_ts": T0 + 8, "filled_ts": T0 + 195}
    monkeypatch.setattr(store, "list_recent", lambda limit=100: [])
    assert flatten.closes_sold(result, venue="paper")[0]["opened_by"] is None


# ── the Time & Sales socket carries the gate's answer ─────────────────────


def test_the_tape_socket_sends_the_gates_answer_on_pings_and_when_it_changes(monkeypatch):
    from fastapi.testclient import TestClient

    from ibkr import tape_stream
    from line_lending import socket_gate

    ws_mod = trading_tape_ws

    lock = {"code": TAPE_STALE, "reason": "r", "text": "GENK's Time & Sales is missing trades. Flatten and cancels still work."}
    answers = iter([lock, lock, None])
    monkeypatch.setattr(ws_mod, "desk_connected", lambda: True)
    monkeypatch.setattr(ws_mod, "is_replay_desk", lambda: False)
    monkeypatch.setattr(ws_mod, "_silence", lambda symbol, halt_seen_at: None)
    monkeypatch.setattr(ws_mod, "_gate", lambda symbol: next(answers))
    monkeypatch.setattr(ws_mod, "MARKET_VIEW_GATE_SEND_SEC", 0.0)

    async def gate(symbol, front=False):
        return None

    monkeypatch.setattr(socket_gate, "gate", gate)
    monkeypatch.setattr(socket_gate, "opened", lambda symbol, **kw: 1)
    monkeypatch.setattr(socket_gate, "closed", lambda symbol, token, kind: None)
    monkeypatch.setattr(socket_gate, "lent_now", lambda symbol, front=False: None)
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda symbol: True)
    monkeypatch.setattr(tape_stream, "ws_viewer_opened", lambda symbol: None)
    monkeypatch.setattr(tape_stream, "ws_viewer_closed", lambda symbol: False)
    monkeypatch.setattr(tape_stream, "open_viewer_queue", lambda symbol: object())
    monkeypatch.setattr(tape_stream, "close_viewer_queue", lambda symbol, queue: None)
    prints = [{"type": "print", "symbol": "GENK", "price": 2.35, "size": 1}]

    async def stream(_queue):
        yield None          # idle: a ping with the gate's answer
        yield prints        # prints flow; the answer is the same, so no frame
        yield prints        # the answer changed: a gate frame

    monkeypatch.setattr(tape_stream, "stream_batches", stream)
    with TestClient(app).websocket_connect("/ws/ibkr/tape/GENK?tab=1&front=1") as ws:
        assert ws.receive_json()["type"] == "subscribed"
        ping = ws.receive_json()
        assert ping["type"] == "ping" and ping["gate"]["code"] == TAPE_STALE
        assert ws.receive_json()["type"] == "print"
        assert ws.receive_json()["type"] == "print"
        assert ws.receive_json() == {"type": "gate", "symbol": "GENK", "gate": None}
