"""Claude's seat on Paper (ADR 068): the seat and its lease, the Level 2 line kept for it, its limits, and its
orders end to end through the real execution door and the real Paper broker on a scratch account.

The market is faked (last / bid / ask by symbol, prints for a break); the clock is pinned to Wednesday 2026-10-07.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from agent_trader import clock as agent_clock
from agent_trader import ledger, lines, rules, seat, view, watcher
from agent_trader.constants_agent_trader import AGENT_LEASE_SEC, SEAT_IN, SEAT_SET, SEAT_WAITING, SEAT_YIELDED
from execution import inflight, service, telemetry
from execution import venue_door
from execution.models import ExecutionCommand
from ibkr import client as ibkr_client
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue
from tests.bot_helpers import headers

ET = ZoneInfo("America/New_York")


def at(clock: str, day: str = "2026-10-07") -> float:
    return datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ET).timestamp()


@pytest.fixture(autouse=True)
def _fresh_seat():
    seat.reset_for_tests()
    lines.reset_for_tests()
    watcher.reset_for_tests()
    yield
    seat.reset_for_tests()
    lines.reset_for_tests()
    watcher.reset_for_tests()


# -- the seat ---------------------------------------------------------------------------------------------
def test_one_holder_at_a_time_and_a_lapsed_lease_frees_the_seat():
    token, _ = seat.claim(now=1000.0)
    none, taken = seat.claim(now=1000.0 + AGENT_LEASE_SEC - 1)
    assert none is None and taken.code == "AGENT_SEAT_TAKEN"
    assert seat.refusal("not-the-token").status == 403
    assert seat.refusal(token) is None and seat.beat("not-the-token") is not None
    assert seat.lapsed(1000.0 + AGENT_LEASE_SEC + 1)
    second, why = seat.claim(now=1000.0 + AGENT_LEASE_SEC + 1)
    assert why is None and second != token


def test_the_seat_survives_a_restart_and_refuses_a_file_it_does_not_know():
    token, _ = seat.claim(now=1000.0)
    seat.set_symbol("SMPL", now=1001.0)
    seat.reset_for_tests()                                   # a restart: the state is read back from the file
    assert seat.holder() == token and seat.symbol() == "SMPL"
    seat.path().write_text(json.dumps({"schema_version": 99, "holder": "x"}), encoding="utf-8")
    seat.reset_for_tests()
    assert seat.holder() is None                              # an unknown file starts with the seat off


# -- the line kept for Claude -----------------------------------------------------------------------------
@pytest.fixture
def depth_lines(monkeypatch):
    """Depth lines and their viewer counts, by symbol."""
    import ibkr.depth as depth

    book: dict[str, int] = {}
    monkeypatch.setattr(depth, "subscribed_symbols", lambda: list(book))
    monkeypatch.setattr(depth, "viewer_count", lambda s: book.get(s, 0))
    return book


def test_the_desk_keeps_two_lines_of_its_own_while_the_seat_is_on(depth_lines):
    depth_lines.update({"SPIK": 1, "FLTX": 1})
    assert lines.desk_refusal("RUNR") is None                 # seat off: all 3 are the desk's
    seat.claim()
    why = lines.desk_refusal("RUNR")
    assert why and "SPIK and FLTX are yours" in why and "Claude" in why
    assert lines.desk_refusal("SPIK") is None                 # a symbol already on a line costs nothing
    assert lines.desk_free(busy=2) == 0
    seat.set_yielded(True, "test")
    assert lines.desk_refusal("RUNR") is None                 # the operator took Claude's line back


def test_a_line_claude_shares_with_a_tab_is_the_desks(depth_lines):
    seat.claim()
    lines._held["SMPL"] = {"depth": True, "tape": True}
    depth_lines.update({"SMPL": 2})                           # Claude and a tab both watch SMPL
    assert lines.desk_lines() == ["SMPL"] and lines.claude_only_lines() == 0
    assert lines.desk_refusal("RUNR") is None                 # the desk's 2nd line
    depth_lines["RUNR"] = 1
    assert lines.desk_refusal("GAPX") is not None             # its 3rd waits
    depth_lines["SMPL"] = 1                                   # the tab closed: SMPL is Claude's alone
    assert lines.claude_only_lines() == 1 and lines.desk_free(busy=2) == 1


def test_a_reconnect_does_not_leave_claude_thinking_it_holds_its_line(depth_lines, monkeypatch):
    """Codex review on PR #1239: a reference outlives an IBKR session, so 'held' must mean 'up now'; Nova's renewal
    of Claude's own line passes Claude's reservation; and Claude asks again without a second reference."""
    import ibkr.depth as depth_mod
    from ibkr import tape_stream

    seat.claim()
    live = {"SMPL": True}
    asked: list[tuple[str, bool]] = []
    opened: list[str] = []

    async def _subscribe(sym, *, live=False, agent=False):
        asked.append((sym, agent))
        live_now[sym] = True
        return {"ok": True}

    live_now = live
    monkeypatch.setattr(depth_mod, "is_live", lambda s: live_now.get(s, False))
    monkeypatch.setattr(depth_mod, "subscribe_async", _subscribe)
    monkeypatch.setattr(depth_mod, "ws_viewer_opened", lambda s: opened.append(s))
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda s: True)
    lines._held["SMPL"] = {"depth": True, "tape": True}
    depth_lines.update({"SPIK": 1, "FLTX": 1, "SMPL": 1})
    assert lines.holds_depth("SMPL")
    live_now["SMPL"] = False                                  # IBKR's session ended; the reference is still counted
    assert not lines.holds_depth("SMPL")
    assert lines.desk_refusal("SMPL") is None                 # line_session's renewal of Claude's line is admitted
    assert lines.desk_refusal("RUNR") is not None             # the desk's 3rd still waits
    assert asyncio.run(lines.acquire("SMPL")) is None
    assert asked == [("SMPL", True)] and opened == []         # asked again, no second viewer reference
    assert lines.holds_depth("SMPL")


def test_claudes_status_never_carries_an_exceptions_text(monkeypatch):
    """CodeQL on PR #1239: a failed Paper read says fixed words; the detail goes to the log only."""
    def _boom():
        raise ledger.ReadError("Traceback ... C:/secret/path.py line 12")

    monkeypatch.setattr(ledger, "fills_today", _boom)
    assert view.status()["read_error"] == ledger.UNREAD_TEXT
    assert rules.day_refusal(0, 0.0) is None


def test_the_depth_door_refuses_a_desk_line_past_two_and_takes_claudes(monkeypatch):
    import importlib

    import ibkr.client as client_mod
    import ibkr.depth as depth_mod
    from tests.test_depth_stability import _FakeContract, _FakeIb

    importlib.reload(depth_mod)
    depth_mod.reset_all()
    fake_ib = _FakeIb()
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "is_ready", lambda: True)
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(depth_mod, "_load_ib_types", lambda: True)
    monkeypatch.setattr(depth_mod, "_Stock", lambda symbol, *a, **k: _FakeContract(0, symbol))
    depth_mod._subscribe_lock = None
    seat.claim()
    for sym in ("SPIK", "FLTX"):
        assert asyncio.run(depth_mod.subscribe_async(sym))["ok"]
        depth_mod.ws_viewer_opened(sym)
    third = asyncio.run(depth_mod.subscribe_async("RUNR"))
    assert third["ok"] is False and third["agent_reserved"] is True and "Claude" in third["error"]
    assert asyncio.run(depth_mod.subscribe_async("SMPL", agent=True))["ok"]
    assert sorted(depth_mod.subscribed_symbols()) == ["FLTX", "SMPL", "SPIK"]
    depth_mod.reset_all()


def test_the_level_2_panel_says_the_line_is_claudes():
    from line_lending.view import cap_words
    from routes.trading_depth_ws import refusal_text

    text = "All 3 Level 2 lines are in use: SPIK and FLTX are yours, SMPL is Claude's."
    assert refusal_text("RUNR", {"cap": True, "agent_reserved": True, "error": text}) == text
    words = cap_words("RUNR", [{"symbol": "SMPL", "held_by": "agent"}, {"symbol": "SPIK", "held_by": "tab"}])
    assert "SMPL Claude's" in words


# -- Claude's limits --------------------------------------------------------------------------------------
ORDER = {"symbol": "SMPL", "qty": 600, "entry": 4.21, "stop": 4.00, "target": 4.60}


@pytest.mark.parametrize(("change", "words"), [
    ({"qty": 1200}, "over Claude's 1,000"),
    ({"stop": 3.90}, "over Claude's $150"),
    ({"stop": 4.25}, "under the entry"),
    ({"stop": None}, "carries a stop"),
    ({"target": 4.10}, "above the entry"),
    ({"qty": 10.5}, "whole number"),
    ({"target2": 4.90}, "first half's shares"),
    ({"trigger": 4.30}, "trigger"),
])
def test_an_entry_outside_claudes_limits_is_refused_in_words(change, words):
    assert words in (rules.shape_refusal({**ORDER, **change}) or "")


def test_an_entry_inside_the_limits_passes():
    assert rules.shape_refusal(ORDER) is None
    assert rules.shape_refusal({**ORDER, "target2": 4.90, "target1_qty": 300, "trigger": 4.15}) is None


def test_the_day_window_and_the_day_stop():
    assert rules.window_refusal(datetime(2026, 10, 7, 6, 59, tzinfo=ET))
    assert rules.window_refusal(datetime(2026, 10, 7, 10, 0, tzinfo=ET)) is None
    assert rules.window_refusal(datetime(2026, 10, 7, 15, 30, tzinfo=ET))
    assert rules.window_refusal(datetime(2026, 10, 10, 10, 0, tzinfo=ET))      # a Saturday
    assert "3 of its 3" in (rules.day_refusal(3, 0.0) or "")
    assert "done for today" in (rules.day_refusal(1, -500.0) or "")
    assert rules.day_refusal(2, -499.0) is None


# -- Paper only -------------------------------------------------------------------------------------------
def _cmd(**kw):
    base = dict(operation="place", idempotency_key="k", source="bot", origin="claude", symbol="SMPL", side="BUY",
                qty=1.0, order_type="LMT", limit_price=1.0)
    return ExecutionCommand(**{**base, **kw})


def test_a_claude_send_never_goes_anywhere_but_paper():
    assert venue_door.wrong_venue(_cmd(), "live") and venue_door.wrong_venue(_cmd(), "sim")
    assert venue_door.wrong_venue(_cmd(), "paper") is None
    close = _cmd(source="flatten", side="SELL", order_type="MKT", limit_price=None, target_venue="live")
    assert "Claude trades Paper only" in (venue_door.target_refusal(close) or "")
    assert venue_door.target_refusal(_cmd(source="flatten", side="SELL", order_type="MKT", limit_price=None,
                                          target_venue="paper")) is None


def test_claudes_fills_count_on_the_bots_line():
    from loss_limit.accounts import by_of

    assert by_of({"order_source": "bot", "order_origin": "claude"}) == "bots"
    assert by_of({"order_source": "flatten", "order_origin": "claude"}) == "bots"


def test_claudes_lane_is_not_stopped_by_the_shared_paper_line(monkeypatch):
    """Operator 2026-10-26: Claude's lane has its own -$500; the desk's shared lines do not refuse its Paper buys."""
    from loss_limit import gate

    monkeypatch.setattr(gate, "stopped", lambda venue, actor=None: {"text": "Daily loss limit reached on Paper"})
    assert gate.buy_refusal("BUY", "bot", "paper", origin="claude") is None
    assert gate.buy_refusal("BUY", "manual", "paper") is not None
    assert gate.buy_refusal("BUY", "bot", "live", origin="claude") is not None   # never a pass anywhere but Paper


def test_claude_never_unlocks_a_padlock_the_operator_locked():
    reset_venue()
    set_venue("paper")
    try:
        _safety.arm(False, actor="operator")
        assert _safety.locked_by() == "operator"
        assert _safety.arm(True, actor="operator") == (None, "")
        assert _safety.locked_by() is None
    finally:
        _safety.arm(False, actor="test")
        _safety._locked_by = None
        reset_venue()


# -- end to end on Paper ----------------------------------------------------------------------------------
class Market:
    def __init__(self) -> None:
        self.px = {"SMPL": [4.20, 4.19, 4.21], "GAPX": [1.90, 1.89, 1.91]}
        self.prints: list[tuple[float, float]] = []
        self.now = at("10:30:00")

    def reference(self, symbol):
        got = self.px.get(symbol)
        return Reference(*got, live=True) if got else Reference(None, live=True)

    def admission(self, symbol):
        return (True, "OK", None) if symbol in self.px else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol, after_ts, through_ts):
        return [p for p in self.prints if after_ts < p[0] <= through_ts]

    def bid_at(self, symbol, ts):
        return self.px[symbol][1]

    def now_ts(self):
        return self.now

    def session_close_ts(self, ts):
        return ts + 86_400


@pytest.fixture
def paper(monkeypatch, short_market_open):
    """The desk on Paper and armed, Claude's line on SMPL, the view lock clear, the clock 10:30 ET."""
    import market
    from market_view import gate

    reset_venue()
    reset_brokers()
    for mod in (service, inflight, telemetry):
        mod.reset_for_tests()
    m = Market()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: m)
    monkeypatch.setattr("practice.reference.LiveReference", lambda: m)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    monkeypatch.setattr(ibkr_client, "is_ready", lambda: True)
    from short_sale import whatif

    async def _no_answer(*args, **kwargs):
        return None

    monkeypatch.setattr(whatif, "request", lambda *a, **k: False)
    monkeypatch.setattr(whatif, "ask", _no_answer)
    monkeypatch.setattr(market, "now_et", lambda: datetime.fromtimestamp(m.now, tz=ET))
    monkeypatch.setattr(agent_clock, "now", lambda: m.now)
    monkeypatch.setattr(gate, "desk_lock", lambda symbol, **kw: None)

    async def _hold(symbol):
        lines._held.clear()
        lines._held[symbol.upper()] = {"depth": True, "tape": True}
        return None

    import ibkr.depth as depth_mod
    from ibkr import tape_stream

    monkeypatch.setattr(lines, "acquire", _hold)
    monkeypatch.setattr(depth_mod, "is_live", lambda s: s.upper() in lines._held)
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda s: s.upper() in lines._held)
    monkeypatch.setenv("NOVA_API_KEY", "agent-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    from main import app

    yield SimpleNamespace(market=m, broker=for_venue("paper"), client=TestClient(app), key=headers("agent-test-key"))
    for mod in (service, inflight, telemetry):
        mod.reset_for_tests()
    reset_brokers()
    reset_venue()


def _seat(p) -> dict:
    got = p.client.post("/api/agent/trader/seat", headers=p.key)
    assert got.status_code == 200, got.text
    h = {**p.key, "X-Agent-Seat": got.json()["token"]}
    watched = p.client.post("/api/agent/trader/watch", headers=h, json={"symbol": "SMPL"})
    assert watched.status_code == 200, watched.text
    return h


def test_a_limit_entry_rests_its_stop_and_target_with_it_on_paper(paper):
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 600, "entry": 4.10, "stop": 3.90, "target": 4.60,
        "why": "FDA clearance, float 3.1M, no offering on file"})
    assert got.status_code == 200, got.text
    rows = ledger.working()
    assert {r["leg_role"] for r in rows} == {"parent", "target", "stop"}
    assert all(r["order_origin"] == "claude" and r["order_source"] == "bot" for r in rows)
    status = got.json()["status"]
    assert status["state"] == SEAT_SET and status["note"]["text"].startswith("FDA")
    assert status["text"] == "Claude · Buy set SMPL 4.10"


def test_an_entry_fills_then_nova_sells_claudes_shares_at_1555(paper):
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 500, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    assert got.status_code == 200, got.text
    assert ledger.position("SMPL") == 500                     # marketable: filled at the ask
    assert view.status()["state"] == SEAT_IN
    paper.market.now = at("15:55:30")
    asyncio.run(watcher.run_pass(now=paper.market.now))
    assert ledger.position("SMPL") == 0 and not ledger.working()


def test_shares_nova_sells_for_claude_leave_claudes_books(paper):
    """Codex review on PR #1239: the Bots line's Auto sell closes Claude's shares under its own origin."""
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    assert got.status_code == 200 and ledger.position("SMPL") == 100
    for row in ledger.working():
        asyncio.run(service.execute(ExecutionCommand(
            operation="cancel", idempotency_key=f"ll-cancel-{row['order_id']}", source="cancel_working",
            symbol="SMPL", order_id=int(row["order_id"]), target_venue="paper", origin="loss_limit_bots"),
            wait_ack=False))
    paper.market.px["SMPL"] = [4.30, 4.29, 4.31]
    sold = asyncio.run(service.execute(ExecutionCommand(
        operation="place", idempotency_key="ll-sell", source="flatten", origin="loss_limit_bots", symbol="SMPL",
        side="SELL", qty=100.0, order_type="MKT", outside_rth=True, skip_risk=True, target_venue="paper",
        intent="flatten"), wait_ack=False))
    assert sold.ok, sold.error
    assert paper.broker.ledger.held_qty("SMPL") == 0
    assert ledger.position("SMPL") == 0 and ledger.positions() == {}
    assert ledger.others_in("SMPL") is None                   # no phantom shares blocking the next trade
    assert 6.0 < ledger.day_pnl() < 8.0                       # bought at the 4.21 ask, sold at the 4.29 bid, less fees
    assert asyncio.run(watcher.end_seat("test")) == []        # nothing left to sell


def test_claude_will_not_trade_a_stock_someone_else_holds(paper):
    h = _seat(paper)
    receipt = asyncio.run(service.execute(ExecutionCommand(
        operation="place", idempotency_key="operator-buy", source="manual", symbol="SMPL", side="BUY", qty=100.0,
        order_type="LMT", limit_price=4.25, skip_risk=True), wait_ack=False))
    assert receipt.ok, receipt.error
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.10, "stop": 4.00, "target": 4.60, "why": "x"})
    assert got.status_code == 409 and got.json()["detail"]["reason"] == "AGENT_NOT_MINE"


def test_the_desk_on_live_refuses_claudes_entry(paper):
    h = _seat(paper)
    set_venue("live")
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.10, "stop": 4.00, "target": 4.60, "why": "x"})
    assert got.status_code == 409 and got.json()["detail"]["reason"] == "AGENT_NOT_PAPER"


def test_a_break_sends_its_bracket_when_a_print_reaches_the_trigger(paper):
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "break", "symbol": "SMPL", "qty": 400, "trigger": 4.30, "top": 4.34, "stop": 4.05, "target": 4.80,
        "why": "over the 4.30 seller"})
    assert got.status_code == 200, got.text
    assert not ledger.working() and len(seat.breaks()) == 1
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    assert not ledger.working()                              # no print at 4.30 yet
    paper.market.px["SMPL"] = [4.31, 4.30, 4.32]
    paper.market.prints.append((paper.market.now + 2, 4.31))
    asyncio.run(watcher.run_pass(now=paper.market.now + 3))
    assert not seat.breaks()
    assert ledger.position("SMPL") == 400                    # bought up to 4.34, at the 4.32 ask
    assert {r["leg_role"] for r in ledger.working()} == {"target", "stop"}


def test_a_quiet_claude_is_closed_out_and_the_seat_freed(paper):
    h = _seat(paper)
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 300, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    assert ledger.position("SMPL") == 300
    asyncio.run(watcher.run_pass(now=float(seat.snapshot()["beat_at"]) + AGENT_LEASE_SEC + 5))
    assert ledger.position("SMPL") == 0 and not ledger.working()
    assert seat.holder() is None and lines.held_symbol() is None


def test_take_claudes_line_stops_new_trades_and_keeps_the_stop(paper):
    h = _seat(paper)
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 300, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    got = paper.client.post("/api/agent/trader/yield", headers=paper.key)
    assert got.status_code == 200 and got.json()["state"] == SEAT_IN
    assert "stop" in {r["leg_role"] for r in ledger.working()} and lines.held_symbol() is None
    again = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.10, "stop": 4.00, "target": 4.60, "why": "x"})
    assert again.json()["detail"]["reason"] == "AGENT_YIELDED"
    paper.client.post("/api/agent/trader/close", headers=h, json={"symbol": "SMPL"})
    assert view.status()["state"] == SEAT_YIELDED


def test_stop_claude_cancels_sells_and_frees_everything(paper):
    h = _seat(paper)
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 300, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    got = paper.client.post("/api/agent/trader/stop-claude", headers=paper.key)
    assert got.status_code == 200 and got.json()["problems"] == []
    assert ledger.position("SMPL") == 0 and seat.holder() is None


def test_the_seat_waits_for_a_line_and_says_why(paper, monkeypatch):
    async def _full(symbol):
        return "All 3 Level 2 lines are in use"

    monkeypatch.setattr(lines, "acquire", _full)
    _seat(paper)
    status = view.status()
    assert status["state"] == SEAT_WAITING and "All 3" in status["text"]
    assert any(e["kind"] == "line_wait" for e in status["events"])
