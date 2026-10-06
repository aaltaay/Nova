"""Who trades the stock (ADR 037, ADR 042 F): one owner, one set of rules.

The per-stock switch, Auto-entry by the bot's rules, Approve, taking over the exit, the persisted
trades and leaving a venue. The trade tests run the real execution door and the real practice broker
on the Paper venue against a fake live market (``FakeLive``), and drive the runner one tick at a time
with a pinned clock.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bot.arming import issue_arm_token
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.first_pullback import orders as fp_orders
from bot.first_pullback import runner as bot_runner
from bot.persist import load_session, save_session
from execution import inflight
from ibkr import safety as _safety
from main import app
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue
from stock_mode import runner, store
from tests.bot_helpers import headers, hold_depth_line, list_hot, ready_l2

NOW = 1_790_000_000.0
SYM = "IMCC"
client = TestClient(app)


class FakeLive:
    """A live market that prices IMCC at 9.98 x 10.02 (last 10.00) and never prints on its own."""

    def __init__(self) -> None:
        self.now = NOW
        self.bid, self.ask, self.last = 9.98, 10.02, 10.00

    def reference(self, symbol: str) -> Reference:
        if symbol != SYM:
            return Reference(None, live=True)
        return Reference(self.last, self.bid, self.ask, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYM else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "stock-mode-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "stock-mode-test-key"


@pytest.fixture
def paper(monkeypatch, api_key):
    """Paper venue, the desk armed, a fake live market, the runner's clock pinned -- and the bot Active
    with the first pullback at Strategy (Auto-entry follows the bot's rules, ADR 042)."""
    reset_venue()
    reset_brokers()
    inflight.reset_for_tests()
    store.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    clock = {"t": NOW}
    runner.reset_for_tests(lambda: clock["t"])
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    issue_arm_token()
    hold_depth_line(SYM)
    list_hot()                            # today's 04:00 reset has run; IMCC is not starred (it needs not be)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake, clock=clock, key=api_key)
    runner.reset_for_tests()
    store.reset_for_tests()
    inflight.reset_for_tests()
    reset_brokers()
    reset_venue()


def trigger(**over) -> dict:
    setup = {"kind": "first_pullback", "trigger": 10.01, "entry": 10.02, "stop": 9.89, "risk": 0.13,
             "target1": 10.28, "triggered_at": NOW, "trigger_price": 10.02, "nth": 1}
    setup.update(over.pop("setup", {}))
    event = {"symbol": SYM, "setup_id": f"{SYM}-2026-09-24-1790000000", "setup": setup,
             "tape": {"verdict": "go", "reasons": ["green on the tape"]}, "ts": NOW,
             "template_id": "default", "template_rev": 1, "template_name": "Default",
             "setup_type": "first_pullback", "source": "live", "grade": "A",
             "pillars": {"passed": 5, "known": 5, "total": 5}, "filtered": None, "spread": 0.02}
    event.update(over)
    return event


def tick(p, at: float | None = None) -> dict | None:
    if at is not None:
        p.clock["t"] = at
        p.ref.now = at
    asyncio.run(runner.tick())
    return store.trade("paper", SYM)


def put(p, buy: str, sell: str, risk: float | None = None, sym: str = SYM):
    body = {"buy": buy, "sell": sell}
    if risk is not None:
        body["risk_usd"] = risk
    return client.put(f"/api/stock-mode/{sym}", json=body, headers=headers(p.key))


def mode_rows(outcome: str | None = None) -> list[dict]:
    return [r for r in list_entries(limit=100)
            if r["action"] == "stock_mode" and (outcome is None or r["outcome"] == outcome)]


def sleeve(**caps) -> None:
    apply_patch({"caps": caps}, desk=True)


# -- the switch ---------------------------------------------------------------------------
def test_every_stock_starts_at_signal_only_with_nothing_locked_on_paper(paper):
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert body["mode"] == "signal" and (body["buy"], body["sell"]) == ("you", "you")
    assert body["locks"] == {"buy": None, "sell": None} and body["venue"] == "paper"
    assert body["trade"] is None and body["approval"] is None and body["notes"] == []
    assert body["risk_usd"] == 20.0 and body["size"] is None                # the venue sleeve's risk per trade
    assert body["entries_today"] == {"count": 0, "cap": 1} and body["nova_entries_today"] == 0


def test_writes_need_the_desk_key(paper):
    assert client.put(f"/api/stock-mode/{SYM}", json={"buy": "nova", "sell": "you"}).status_code == 401


def test_on_live_both_nova_sides_are_locked_and_say_why(paper):
    set_venue("live")
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert "never buys by itself" in body["locks"]["buy"] and "#604" in body["locks"]["sell"]
    r = put(paper, "nova", "you")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_LIVE"
    r = put(paper, "you", "nova")
    assert r.status_code == 409 and "#604" in r.json()["detail"]["error"]
    assert put(paper, "you", "you").status_code == 200        # Signal only is always allowed


def test_on_live_a_listed_stock_still_reads_you_you(paper):
    set_venue("live")
    row = load_session()
    row["symbol_allowlist"] = [SYM]                           # a list that should never be on Live
    save_session(row)
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert (body["buy"], body["sell"], body["mode"]) == ("you", "you", "signal")


def test_off_the_live_edge_sim_is_a_replay_and_nova_is_locked(paper):
    set_venue("sim")                                          # conftest pins the live edge off
    r = put(paper, "nova", "you")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_REPLAY"


def test_put_ignores_a_risk_it_is_sent(paper):
    body = put(paper, "nova", "you", risk=0.5).json()        # out of any bound: ignored, not an error
    assert body["mode"] == "auto_entry" and body["risk_usd"] == 20.0


def test_the_four_modes_and_one_mode_per_stock(paper):
    assert put(paper, "nova", "you").json()["mode"] == "auto_entry"
    assert put(paper, "you", "nova").json()["mode"] == "approve"
    body = put(paper, "nova", "nova").json()
    assert body["mode"] == "bot" and body["bot"]["on_list"] is True and store.switch(SYM) is None
    assert SYM in load_session()["symbol_allowlist"]
    assert put(paper, "nova", "you").json()["mode"] == "auto_entry"
    assert SYM not in load_session()["symbol_allowlist"]       # Bot and Auto-entry never stand together
    assert put(paper, "you", "you").json()["mode"] == "signal"
    assert [r["inputs"]["to"] for r in mode_rows("set")] == ["auto_entry", "approve", "bot", "auto_entry", "signal"]
    assert client.get(f"/api/stock-mode/{SYM}").json()["bot"] is None


def test_the_bots_list_is_the_truth_for_bot(paper):
    row = load_session()
    row["symbol_allowlist"] = [SYM]
    save_session(row)
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert body["mode"] == "bot"
    assert body["bot"] == {"on_list": True, "playing": True, "reason": None, "setup_at_strategy": None,
                           "active": True}


def test_sell_never_moves_to_nova_while_the_stock_is_held(paper):
    paper.broker.place(SYM, "BUY", 5, "MKT")
    r = put(paper, "you", "nova")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_HELD"
    assert "You hold IMCC" in r.json()["detail"]["error"]


def test_a_venue_change_returns_every_stock_to_signal_only(paper):
    put(paper, "nova", "you")
    set_venue("sim")
    set_venue("paper")
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert body["mode"] == "signal"


# -- the notes: every blocker, not the first ----------------------------------------------------
def plan_lane(**over) -> dict:
    row = {"setup_id": f"{SYM}-2026-09-24-1790000000", "setup_type": "first_pullback", "state": "armed",
           "reason": "", "grade": "A", "pillars": None, "setup": {"trigger": 10.01, "entry": 10.02, "stop": 9.89,
                                                                  "target1": 10.28, "risk": 0.13}}
    row.update(over)
    return row


def test_notes_say_everything_that_keeps_nova_from_acting(paper, monkeypatch):
    import execution.session_gate as session_gate

    from bot.arming import disarm_session

    put(paper, "nova", "you")
    disarm_session()
    apply_patch({"setup_levels": {"first_pullback": 1}}, desk=True)
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "disarmed"))
    monkeypatch.setattr(session_gate, "regular_hours_now", lambda: False)
    monkeypatch.setattr("stock_mode.view._plan_lane", lambda sym, now: plan_lane(grade="C"))
    from tests.bot_helpers import release_depth_lines, open_entry_window

    release_depth_lines()
    open_entry_window(hour=12)
    sleeve(extended_hours=False)          # on by default (ADR 042 E): the operator turned it off
    notes = {n["id"]: n["text"] for n in client.get(f"/api/stock-mode/{SYM}").json()["notes"]}
    assert "padlock" in notes["padlock"]
    assert "does not follow IMCC" in notes["not_followed"]
    assert "Not a trade: grade C" in notes["not_a_trade"]
    assert "not active" in notes["not_active"]
    assert "first pullback is at Eyes" in notes["not_strategy"]
    assert "Outside the bot's window" in notes["window"]
    assert "extended hours" in notes["extended_hours"]
    assert "no Level 2 line" in notes["no_depth"]


def test_the_notes_never_hold_a_stock_off_the_hot_list(paper):
    """ADR 044, amended 2026-10-06: a star is watching, never permission -- the Who trades view of a stock off
    today's list promises the buy without a word about the list."""
    import hot_list

    put(paper, "nova", "you")
    assert not hot_list.is_listed(SYM)
    said = client.get(f"/api/stock-mode/{SYM}").json()["notes"]
    assert not {"not_listed", "hot_list_default", "day_reset"} & {n["id"] for n in said}
    assert [n for n in said if "hot list" in n["text"]] == []


def test_the_notes_say_the_bot_buys_nothing_before_todays_reset(paper):
    """Until today's 04:00 reset of yesterday's bot buys has run, a Nova-buy stock's view says nothing buys yet;
    a stock at Signal only gets no such note."""
    from constants_hot_list import HOT_LIST_FILE
    from paths import cache_dir

    (cache_dir() / HOT_LIST_FILE).unlink()
    assert "day_reset" not in {n["id"] for n in client.get(f"/api/stock-mode/{SYM}").json()["notes"]}
    put(paper, "nova", "you")
    said = client.get(f"/api/stock-mode/{SYM}").json()["notes"]
    [note] = [n for n in said if n["id"] == "day_reset"]
    assert note == {"id": "day_reset", "tone": "warn",
                    "text": "The bot buys nothing yet: the 04:00 ET reset of yesterday's bot buys has not run yet "
                            "today (it runs within 30 s of 04:00 and at every start)."}
    list_hot()
    assert "day_reset" not in {n["id"] for n in client.get(f"/api/stock-mode/{SYM}").json()["notes"]}


def test_the_view_says_the_size_nova_would_send(paper, monkeypatch):
    monkeypatch.setattr("stock_mode.view._plan_lane", lambda sym, now: plan_lane())
    put(paper, "nova", "you")
    size = client.get(f"/api/stock-mode/{SYM}").json()["size"]
    assert size["qty"] == 1 and size["by_risk"] == 153 and size["capped_by"] == "max_shares"
    sleeve(max_shares=10, bp_budget_usd=35.0)
    size = client.get(f"/api/stock-mode/{SYM}").json()["size"]
    assert size["qty"] == 3 and size["capped_by"] == "budget"
    put(paper, "you", "nova")
    size = client.get(f"/api/stock-mode/{SYM}").json()["size"]
    assert size["qty"] == 153 and size["capped_by"] is None and "you approve it" in size["text"]


# -- Auto-entry: the bot's rules, the exit handed to you -------------------------------------------
def test_auto_entry_buys_the_go_trigger_sized_by_the_sleeve_and_never_sells(paper):
    put(paper, "nova", "you")
    runner.submit(trigger())
    trade = tick(paper)
    assert trade["kind"] == "auto_entry" and trade["qty"] == 1 and trade["ttl_sec"] == 3
    assert "capped at the sleeve's 1 max share" in trade["size_text"]
    trade = tick(paper, NOW + 0.5)                                    # marketable at the ask: filled in the send
    assert trade["state"] == "holding" and trade["exits"] == "you" and trade["fill_price"] == 10.02
    assert paper.broker.ledger.held_qty(SYM) == 1.0
    assert paper.broker.ledger.working_orders() == []                 # no target, no stop: the exit is yours
    fills = [r for r in paper.broker.ledger.closed_orders() if r["status"] == "Filled"]
    assert {r["order_source"] for r in fills} == {"bot"}
    assert [r["outcome"] for r in mode_rows()][-2:] == ["sent", "filled"]
    view = client.get(f"/api/stock-mode/{SYM}").json()
    assert view["trade"]["exits"] == "you" and view["nova_entries_today"] == 1
    assert view["entries_today"] == {"count": 1, "cap": 1}
    assert "the exit is yours" in view["last_event"]["text"]


def test_no_new_entry_starts_while_the_desk_is_leaving_the_venue(paper, monkeypatch):
    """ADR 042 F: while the sweep cancels Nova's working entries on the venue the desk leaves, a
    trigger heard meanwhile sends nothing there -- it is skipped, and says why."""
    import stock_mode.leave as leave

    put(paper, "nova", "you")
    monkeypatch.setattr(leave, "_leaving", ("paper", "live"))
    runner.submit(trigger())
    assert tick(paper) is None
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == "BOT_VENUE_CHANGING"
    assert "moving from paper to live" in skip["reason"]
    assert paper.broker.ledger.working_orders() == []


def test_auto_entry_and_the_bot_share_one_daily_count(paper):
    put(paper, "nova", "you")
    runner.submit(trigger())
    tick(paper)
    runner.submit(trigger(setup_id="SECOND", ts=NOW + 60, setup={"triggered_at": NOW + 60}))
    tick(paper, NOW + 60)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == "BOT_DAY_TRADE_CAP" and paper.broker.ledger.held_qty(SYM) == 1.0
    assert load_session().get("trade") is None
    notes = {n["id"]: n["text"] for n in client.get(f"/api/stock-mode/{SYM}").json()["notes"]}
    assert notes["daily_cap"].startswith("1 Nova automatic entry a day") and notes["daily_cap"].endswith(".")
    assert {g["id"]: g for g in client.get("/api/bot/session").json()["gates"]}["daily_cap"]["ok"] is False


@pytest.mark.parametrize("event, code, words", [
    (trigger(tape={"verdict": "wait", "reasons": ["a seller at 10.05"]}), "BOT_TAPE_NOT_GO", "the tape read wait"),
    (trigger(tape={"verdict": "blind"}), "BOT_TAPE_NOT_GO", "the tape read blind"),
    (trigger(ts=NOW - 30, setup={"triggered_at": NOW - 30}), "BOT_TRIGGER_STALE", "30s old"),
    (trigger(grade="C", pillars={"passed": 3, "known": 5, "total": 5}), "BOT_NOT_A_TRADE", "grade C: 3 of 5"),
    (trigger(setup={"kind": "second_pullback", "nth": 2}), "BOT_NOT_FIRST_OF_DAY",
     "a 2nd first pullback: this strategy buys the 1st of the day only"),
])
def test_what_keeps_auto_entry_from_buying_is_said(paper, event, code, words):
    put(paper, "nova", "you")
    runner.submit(event)
    tick(paper)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == code and words in skip["reason"]
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    assert client.get(f"/api/stock-mode/{SYM}").json()["last_event"]["text"].startswith("Nova did not buy")


def test_auto_entry_buys_a_stock_off_the_hot_list(paper):
    """ADR 044, amended 2026-10-06: Auto-entry buys a stock whether or not it is starred."""
    import hot_list

    put(paper, "nova", "you")
    assert not hot_list.is_listed(SYM)
    runner.submit(trigger())
    trade = tick(paper)
    assert trade["kind"] == "auto_entry" and mode_rows("skipped") == []


def test_auto_entry_buys_nothing_before_todays_reset_ran(paper):
    """No file for today: yesterday's Auto-entry switches are not known to be reset, so nothing is bought."""
    from constants_hot_list import HOT_LIST_FILE
    from paths import cache_dir

    put(paper, "nova", "you")
    (cache_dir() / HOT_LIST_FILE).unlink()
    runner.submit(trigger())
    tick(paper)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == "BOT_SKIP_DAY_NOT_RESET"
    assert "the 04:00 ET reset of yesterday's bot buys has not run yet today" in skip["reason"]
    assert paper.broker.ledger.held_qty(SYM) == 0.0


def test_auto_entry_needs_the_bot_active_and_the_setup_at_strategy(paper):
    from bot.arming import disarm_session

    put(paper, "nova", "you")
    disarm_session()
    apply_patch({"setup_levels": {"first_pullback": 1}}, desk=True)
    runner.submit(trigger())
    tick(paper)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["codes"][:2] == ["BOT_NOT_ACTIVE", "BOT_SETUP_NOT_STRATEGY"]
    assert "the bot is not active" in skip["reason"] and "first pullback is at Eyes" in skip["reason"]


def test_a_locked_padlock_keeps_auto_entry_from_buying(paper, monkeypatch):
    put(paper, "nova", "you")
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "disarmed"))
    runner.submit(trigger())
    tick(paper)
    [skip] = mode_rows("skipped")
    assert "BOT_PADLOCK_LOCKED" in skip["inputs"]["codes"]


def test_a_stock_on_the_bot_list_never_auto_enters(paper):
    store.set_switch(SYM, {"buy": "nova", "sell": "you", "set_at": NOW})     # a switch left behind
    row = load_session()
    row["symbol_allowlist"] = [SYM]
    save_session(row)
    runner.submit(trigger())
    tick(paper)
    [skip] = mode_rows("skipped")
    assert "set to Bot: the bot trades it, not Auto-entry" in skip["reason"]


def test_an_unfilled_entry_is_cancelled_after_the_sleeves_ttl_as_a_miss(paper):
    put(paper, "nova", "you")
    runner.submit(trigger(setup={"entry": 9.95, "stop": 9.85, "target1": 10.15}))
    trade = tick(paper)
    assert trade["state"] == "entering"                               # 9.95 under the 10.02 ask: it rests
    tick(paper, NOW + 3.5)
    trade = tick(paper, NOW + 4)
    assert trade["state"] == "missed" and "not filled in 3s" in trade["note"]
    assert paper.broker.ledger.working_orders() == []
    assert client.get(f"/api/stock-mode/{SYM}").json()["entries_today"]["count"] == 0    # a miss gives it back


def test_turning_auto_entry_off_cancels_its_working_entry(paper):
    put(paper, "nova", "you")
    runner.submit(trigger(setup={"entry": 9.95, "stop": 9.85, "target1": 10.15}))
    tick(paper)
    assert paper.broker.ledger.working_orders()
    assert put(paper, "you", "you").status_code == 200
    assert paper.broker.ledger.working_orders() == []


def test_the_holding_trade_closes_when_you_sell(paper):
    put(paper, "nova", "you")
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    paper.broker.place(SYM, "SELL", 1, "MKT")
    trade = tick(paper, NOW + 2)
    assert trade["state"] == "closed" and trade["exit_reason"] == "outside"


def test_a_trigger_on_a_signal_only_stock_does_nothing(paper):
    runner.submit(trigger())
    assert tick(paper) is None and mode_rows() == []


# -- persisted trades and leaving a venue ---------------------------------------------------------
def test_a_restart_resumes_managing_the_trade(paper):
    put(paper, "nova", "you")
    runner.submit(trigger(setup={"entry": 9.95, "stop": 9.85, "target1": 10.15}))
    assert tick(paper)["state"] == "entering"
    store.forget_for_tests()                                          # a new process: memory gone, the file stays
    assert store.trade("paper", SYM)["state"] == "entering"
    tick(paper, NOW + 3.5)
    assert tick(paper, NOW + 4)["state"] == "missed"
    assert paper.broker.ledger.working_orders() == []


def test_an_unknown_trades_file_is_refused_loudly_and_never_overwritten(paper):
    from constants_stock_mode import STOCK_MODE_TRADES_FILENAME
    from paths import cache_dir

    path = cache_dir() / STOCK_MODE_TRADES_FILENAME
    path.write_text(json.dumps({"schema_version": 99, "trades": []}), encoding="utf-8")
    store.forget_for_tests()
    put(paper, "nova", "you")
    notes = {n["id"]: n["text"] for n in client.get(f"/api/stock-mode/{SYM}").json()["notes"]}
    assert "could not be read" in notes["trades_unreadable"] and "schema_version=99" in notes["trades_unreadable"]
    runner.submit(trigger())
    tick(paper)
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 99


def test_leaving_the_venue_cancels_nova_entries_there_first(paper):
    put(paper, "nova", "you")
    runner.submit(trigger(setup={"entry": 9.95, "stop": 9.85, "target1": 10.15}))
    assert tick(paper)["state"] == "entering"
    res = client.post("/api/desk/venue", json={"venue": "live"}, headers=headers(paper.key))
    assert res.status_code == 200
    [left] = res.json()["left"]
    assert left == {"venue": "paper", "symbol": SYM, "order_id": left["order_id"], "by": "auto_entry", "ok": True,
                    "text": "Nova's auto-entry buy of IMCC on paper was cancelled: the desk moved to live"}
    assert for_venue("paper").ledger.working_orders() == []
    trade = store.trade("paper", SYM)
    assert trade["state"] == "missed" and "the desk left paper" in trade["note"]


def test_a_venue_change_with_an_unreadable_session_still_moves_and_says_so(paper, monkeypatch):
    def broken():
        raise OSError("bot-session.json is locked")

    monkeypatch.setattr("bot.persist.load_session", broken)
    out = set_venue("live")
    assert out["venue"] == "live"
    [left] = out["left"]
    assert left["ok"] is False and "could not read its working entries on paper" in left["text"]


# -- Approve --------------------------------------------------------------------------------
def lane(state: str = "armed", **over) -> dict:
    setup = {"trigger": 10.01, "entry": 10.02, "stop": 9.89, "target1": 10.28, "risk": 0.13,
             "triggered_at": NOW if state == "triggered" else None}
    setup.update(over.pop("setup", {}))
    row = {"setup_id": f"{SYM}-2026-09-24-1790000000", "setup_type": "first_pullback", "state": state,
           "reason": "", "setup": setup, "grade": "A"}
    row.update(over)
    return row


def approve_body(**over) -> dict:
    body = {"setup_id": f"{SYM}-2026-09-24-1790000000", "entry": 10.02, "stop": 9.89, "target": 10.28, "qty": 153}
    body.update(over)
    return body


class Receipt(SimpleNamespace):
    pass


@pytest.fixture
def sent(monkeypatch):
    """Capture the brackets Nova sends (the practice broker's own bracket tests cover the fills)."""
    calls: list[dict] = []

    async def send_bracket(trade):
        calls.append(dict(trade))
        return Receipt(ok=True, order_id=101, parent_order_id=101, target_order_id=102, stop_order_id=103,
                       error=None, reason_code=None)

    from stock_mode import orders as sm_orders

    monkeypatch.setattr(sm_orders, "send_bracket", send_bracket)
    # the stubbed legs rest at the broker (the practice broker's own bracket tests cover real fills)
    monkeypatch.setattr(sm_orders, "order_row",
                        lambda oid: {"order_id": oid, "status": "Submitted"} if oid in (101, 102, 103) else None)
    return calls


def test_approve_needs_the_approve_mode(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_NOT_APPROVE"


def test_an_approval_binds_to_the_lanes_own_levels(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane(setup={"entry": 9.99, "stop": 9.86}))
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_PLAN_CHANGED"
    assert "9.99 / 9.86 / 10.28" in r.json()["detail"]["error"]


@pytest.mark.parametrize("bad, reason, words", [
    (lane("filtered", reason="filtered: float over 10M", phase="armed"), "STOCK_MODE_FILTERED", "float over 10M"),
    (lane(grade="C", pillars={"checks": {"a": True, "b": False, "c": False, "d": None, "e": True}}),
     "STOCK_MODE_NOT_A_TRADE", "grade C: 2 of 5 pillars"),
    (lane(outcome="stop_first"), "STOCK_MODE_NOT_A_TRADE", "already played out"),
])
def test_approve_refuses_a_filtered_setup_and_a_plan_that_is_not_a_trade(paper, monkeypatch, bad, reason, words):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: bad)
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == reason and words in r.json()["detail"]["error"]
    assert store.approval(SYM) is None


def test_an_approved_plan_is_sent_as_one_bracket_at_its_trigger(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    assert r.status_code == 200 and r.json()["approval"]["state"] == "waiting"
    runner.submit(trigger(setup_id="SOMETHING-ELSE"))
    tick(paper)
    assert sent == []                                                  # another setup's trigger sends nothing
    runner.submit(trigger())
    trade = tick(paper, NOW + 0.2)
    assert [(c["entry"], c["stop"], c["target"], c["qty"], c["ttl_sec"]) for c in sent] == [
        (10.02, 9.89, 10.28, 153, 3)]                                  # the sleeve's TTL
    assert trade["kind"] == "approve" and trade["exits"] == "nova"
    assert (trade["entry_order_id"], trade["target_order_id"], trade["stop_order_id"]) == (101, 102, 103)
    view = client.get(f"/api/stock-mode/{SYM}").json()
    assert view["approval"]["state"] == "sent" and view["entries_today"]["count"] == 0     # counted, never capped


def test_a_trigger_that_is_not_a_trade_withdraws_the_approval_and_says_why(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger(spread=0.20))
    tick(paper)
    assert sent == []
    approval = client.get(f"/api/stock-mode/{SYM}").json()["approval"]
    assert approval["state"] == "withdrawn" and "the spread 0.20 is at least the 0.13 risk" in approval["reason"]


def test_a_trigger_the_tape_does_not_pass_withdraws_the_approval_and_says_why(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger(tape={"verdict": "veto", "reasons": ["spread 0.08"]}))
    tick(paper)
    assert sent == []
    approval = client.get(f"/api/stock-mode/{SYM}").json()["approval"]
    assert approval["state"] == "withdrawn" and "VETO" in approval["reason"]


def test_a_rearm_at_other_levels_withdraws_the_approval(paper, monkeypatch, sent):
    state = {"lane": lane()}
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: state["lane"])
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    state["lane"] = lane(setup={"entry": 9.97, "stop": 9.89, "target1": 10.13})
    tick(paper, NOW + 3)
    approval = client.get(f"/api/stock-mode/{SYM}").json()["approval"]
    assert approval["state"] == "withdrawn" and "re-armed at 9.97" in approval["reason"]


def test_a_setup_the_filter_keeps_out_after_approval_withdraws_it(paper, monkeypatch, sent):
    state = {"lane": lane()}
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: state["lane"])
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    state["lane"] = lane("filtered", reason="filtered: price over 20", phase="armed")
    tick(paper, NOW + 3)
    approval = client.get(f"/api/stock-mode/{SYM}").json()["approval"]
    assert approval["state"] == "withdrawn" and "price over 20" in approval["reason"]


def test_approve_now_sends_on_a_triggered_setup(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane("triggered", trigger_tape={"verdict": "go"}))
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(now=True), headers=headers(paper.key))
    assert r.status_code == 200 and len(sent) == 1 and r.json()["trade"]["kind"] == "approve"
    assert r.json()["approval"]["state"] == "sent"


def test_cancel_approval_before_the_trigger(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    r = client.delete(f"/api/stock-mode/{SYM}/approve", headers=headers(paper.key))
    assert r.status_code == 200 and r.json()["approval"] is None
    runner.submit(trigger())
    tick(paper)
    assert sent == []


# -- taking over ----------------------------------------------------------------------------
def test_nothing_to_take_over_is_said(paper):
    r = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_NOTHING_HELD"


def test_taking_over_the_bots_trade_leaves_buy_on_you(paper, monkeypatch):
    bot_runner.reset_for_tests(lambda: paper.clock["t"])
    ready_l2(brain=None, symbols=(SYM,))
    monkeypatch.setattr(fp_orders, "last_price", lambda symbol: 10.00)
    monkeypatch.setattr(fp_orders, "best_bid", lambda symbol: 9.98)
    bot_runner.submit(trigger())
    asyncio.run(bot_runner.tick())
    assert load_session()["trade"]["state"] == "open"
    assert client.get(f"/api/stock-mode/{SYM}").json()["mode"] == "bot"
    r = client.post(f"/api/stock-mode/{SYM}/take-over", json={"risk_usd": 20}, headers=headers(paper.key))
    assert r.status_code == 200
    bot_trade = load_session()["trade"]
    assert bot_trade["state"] == "handed" and bot_trade["target_order_id"] is None
    assert paper.broker.ledger.working_orders() == [] and paper.broker.ledger.held_qty(SYM) == 1.0
    assert SYM not in load_session()["symbol_allowlist"]
    body = r.json()
    assert body["mode"] == "signal" and body["buy"] == "you"          # never turns into Auto-entry
    assert body["trade"]["exits"] == "you" and body["nova_entries_today"] == 1
    assert any(row["action"] == "bot_trade" and row["outcome"] == "handed" for row in list_entries(limit=50))
    bot_runner.reset_for_tests()


def test_setting_sell_to_you_takes_over_an_approved_bracket(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    cancels: list[int] = []

    async def cancel(trade, order_id, *, source="bot"):
        cancels.append(int(order_id))
        return Receipt(ok=True, order_id=order_id, error=None, reason_code=None)

    from stock_mode import orders as sm_orders

    monkeypatch.setattr(sm_orders, "cancel", cancel)
    monkeypatch.setattr(sm_orders, "order_row", lambda oid: {"order_id": oid, "status": "Filled", "filled_qty": 153,
                                                              "avg_fill_price": 10.02} if oid == 101 else
                        {"order_id": oid, "status": "Submitted"})
    assert put(paper, "you", "nova").status_code == 200
    assert client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key)).status_code == 200
    monkeypatch.setattr(sm_orders, "held_qty", lambda sym: 153.0)     # the stubbed entry filled
    runner.submit(trigger())
    tick(paper)
    trade = tick(paper, NOW + 0.5)
    assert trade["state"] == "holding" and trade["exits"] == "nova"
    body = put(paper, "you", "you").json()
    assert sorted(cancels) == [102, 103] and body["mode"] == "signal"
    assert body["trade"]["exits"] == "you"


def test_a_take_over_whose_cancel_is_refused_keeps_the_trade_and_says_so(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())

    async def cancel(trade, order_id, *, source="bot"):
        if int(order_id) == 103:
            return Receipt(ok=False, order_id=order_id, error="broker said no", reason_code="BROKER_REJECT")
        return Receipt(ok=True, order_id=order_id, error=None, reason_code=None)

    from stock_mode import orders as sm_orders

    monkeypatch.setattr(sm_orders, "cancel", cancel)
    monkeypatch.setattr(sm_orders, "order_row", lambda oid: {"order_id": oid, "status": "Filled", "filled_qty": 153,
                                                              "avg_fill_price": 10.02} if oid == 101 else
                        {"order_id": oid, "status": "Submitted"})
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    monkeypatch.setattr(sm_orders, "held_qty", lambda sym: 153.0)
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    r = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_SEND"
    assert "still rests" in r.json()["detail"]["error"] and "broker said no" in r.json()["detail"]["error"]
    trade = store.trade("paper", SYM)
    assert trade["exits"] == "nova" and trade["target_order_id"] is None and trade["stop_order_id"] == 103
    assert client.get(f"/api/stock-mode/{SYM}").json()["mode"] == "approve"


# -- Approve on the practice broker's own brackets (#606 step 1) -------------------------------
def _legs(p) -> dict[int, dict]:
    ledger = p.broker.ledger
    return {int(r["order_id"]): r for r in [*ledger.working_orders(), *ledger.closed_orders()]}


def test_an_approved_bracket_fills_at_the_broker_and_its_target_closes_the_trade(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger())
    tick(paper)                                              # the bracket goes out: the entry takes the 10.02 ask
    trade = tick(paper, NOW + 0.5)
    assert trade["state"] == "holding" and trade["exits"] == "nova" and trade["fill_price"] == 10.02
    legs = _legs(paper)
    target, stop = legs[trade["target_order_id"]], legs[trade["stop_order_id"]]
    assert (target["leg_role"], target["status"], target["limit_price"]) == ("target", "Submitted", 10.28)
    assert (stop["leg_role"], stop["status"], stop["stop_price"]) == ("stop", "Submitted", 9.89)
    assert target["oca_group"] == stop["oca_group"] == f"oca-{trade['entry_order_id']}"

    paper.broker.try_fill_working(SYM, [(NOW + 2, 10.30)])     # a print through the target
    trade = tick(paper, NOW + 2.5)
    assert (trade["state"], trade["exit_reason"], trade["exit_price"]) == ("closed", "target", 10.28)
    legs = _legs(paper)
    assert legs[trade["stop_order_id"]]["status"] == "Cancelled"
    assert legs[trade["stop_order_id"]]["reason_code"] == "PRACTICE_OCO_CANCELLED"
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    view = client.get(f"/api/stock-mode/{SYM}").json()
    assert view["trade"]["state"] == "closed" and view["trade"]["closed_at"] == NOW + 2.5
    assert "10.28" in view["last_event"]["text"] and "+$39.78" in view["last_event"]["text"]


def test_taking_over_a_real_bracket_cancels_both_exits_and_keeps_the_shares(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger())
    tick(paper)
    trade = tick(paper, NOW + 0.5)
    body = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(paper.key)).json()
    assert body["trade"]["exits"] == "you" and body["mode"] == "signal"
    assert paper.broker.ledger.working_orders() == [] and paper.broker.ledger.held_qty(SYM) == 153.0
    legs = _legs(paper)
    assert {legs[trade["target_order_id"]]["status"], legs[trade["stop_order_id"]]["status"]} == {"Cancelled"}
    paper.broker.try_fill_working(SYM, [(NOW + 3, 10.30), (NOW + 4, 9.80)])
    assert paper.broker.ledger.held_qty(SYM) == 153.0            # Nova sells nothing once the exit is yours


def test_an_approved_entry_left_unfilled_is_cancelled_with_its_exits(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    paper.ref.bid, paper.ref.ask, paper.ref.last = 10.06, 10.10, 10.08     # the entry rests under the ask
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger())
    trade = tick(paper)
    assert trade["state"] == "entering"
    legs = _legs(paper)
    assert {legs[trade["target_order_id"]]["status"], legs[trade["stop_order_id"]]["status"]} == {"PreSubmitted"}
    tick(paper, NOW + 3.5)
    trade = tick(paper, NOW + 4.0)
    assert trade["state"] == "missed"
    legs = _legs(paper)
    assert legs[trade["entry_order_id"]]["status"] == "Cancelled"
    assert {legs[trade["target_order_id"]]["reason_code"], legs[trade["stop_order_id"]]["reason_code"]} == {
        "PRACTICE_PARENT_CANCELLED"}
    assert paper.broker.ledger.working_orders() == [] and paper.broker.ledger.held_qty(SYM) == 0.0


def test_an_unreadable_bot_session_is_said_never_read_as_empty(paper, monkeypatch):
    def broken():
        raise OSError("bot-session.json is locked")

    monkeypatch.setattr("bot.persist.load_session", broken)
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert body["notes"][0]["id"] == "bot_unreadable" and "unknown" in body["notes"][0]["text"]
    assert body["bot"]["reason"] == "the bot session could not be read"
