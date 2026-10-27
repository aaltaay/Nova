"""The seat's tools (ADR 068 decisions 14 and 15, 2026-10-27): it acts on each print, keeps a trade journal, and
survives a restart; a new session picks it up in one call.

End to end on the real Paper broker through the seat suite's ``paper`` fixture (SMPL last 4.20, bid 4.19, ask 4.21).
"""
from __future__ import annotations

import asyncio

import pytest

from agent_trader import guard, journal, ledger, seat, wake, watcher
from agent_trader.constants_agent_trader import AGENT_LEASE_SEC
from tests.test_agent_trader import _fresh_seat, _seat, paper  # noqa: F401 -- fixtures


@pytest.fixture(autouse=True)
def _fresh_tools():
    wake.reset_for_tests()
    journal.reset_for_tests()
    guard.reset_for_tests()
    yield
    wake.reset_for_tests()
    journal.reset_for_tests()
    guard.reset_for_tests()


# -- the live ring ------------------------------------------------------------------------------------------
def test_the_ring_keeps_a_watched_stocks_prints_and_says_how_far_back_it_reaches():
    wake.watch({"SMPL"}, now=100.0)
    wake.print_in({"symbol": "SMPL", "ts": 101.0, "price": 4.3, "size": 100, "bid": 4.29, "ask": 4.31})
    wake.print_in({"symbol": "OTHR", "ts": 101.0, "price": 1.0, "size": 100})           # not watched
    assert [p["price"] for p in wake.prints("SMPL", 100.0)] == [4.3]
    assert wake.prints("SMPL", 99.0) is None                                             # before watching began
    assert wake.prints("OTHR", 0.0) is None
    wake.print_in({"symbol": "SMPL", "ts": 200.0, "price": 4.4, "size": 100})            # 99 s later: the first ages out
    assert wake.prints("SMPL", 120.0) == [{"ts": 200.0, "price": 4.4, "size": 100, "bid": None, "ask": None,
                                            "exchange": None, "conditions": None}]
    assert wake.prints("SMPL", 100.0) is None                                            # trimmed past that
    wake.watch(set())
    assert wake.prints("SMPL", 150.0) is None


def test_a_print_wakes_the_watcher_before_its_tick(monkeypatch):
    """The tick is set to 30 s: only the wake can explain a second pass."""
    passes: list[float] = []

    async def _pass(now=None):
        passes.append(asyncio.get_running_loop().time())

    monkeypatch.setattr(watcher, "run_pass", _pass)
    monkeypatch.setattr(watcher, "_watch_set", lambda: {"SMPL"})
    monkeypatch.setattr(watcher, "AGENT_TICK_SEC", 30.0)

    async def main() -> int:
        task = asyncio.create_task(watcher.run())
        for _ in range(200):
            if passes:
                break
            await asyncio.sleep(0.01)
        wake.print_in({"symbol": "SMPL", "ts": 1.0, "price": 4.3, "size": 100})
        for _ in range(500):
            if len(passes) >= 2:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        return len(passes)

    assert asyncio.run(main()) >= 2


def test_a_break_triggers_on_a_live_print_the_archive_has_not_written(paper):
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "break", "symbol": "SMPL", "qty": 400, "trigger": 4.30, "top": 4.34, "stop": 4.05, "target": 4.80,
        "why": "over the 4.30 seller"})
    assert got.status_code == 200, got.text
    wake.watch({"SMPL"}, now=paper.market.now)
    paper.market.px["SMPL"] = [4.31, 4.30, 4.32]
    wake.print_in({"symbol": "SMPL", "ts": paper.market.now + 1, "price": 4.31, "size": 200})   # not in the archive
    asyncio.run(watcher.run_pass(now=paper.market.now + 1.1))
    assert not seat.breaks() and ledger.position("SMPL") == 400


# -- the journal --------------------------------------------------------------------------------------------
def test_a_trade_is_journaled_with_its_why_snapshots_exit_reason_and_pnl(paper, monkeypatch):
    import ibkr.depth as depth

    book = {"bids": [{"price": 4.20, "size": 900}], "asks": [{"price": 4.21, "size": 700}]}   # 4.19 would be the guard
    monkeypatch.setattr(depth, "current_book", lambda s: book)
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.25, "stop": 4.00, "target": 4.80,
        "why": "FDA clearance, float 3.1M"})
    assert got.status_code == 200 and ledger.position("SMPL") == 100
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    opened = paper.client.get("/api/agent/trader/journal").json()["open"]
    assert opened[0]["why"] == "FDA clearance, float 3.1M" and opened[0]["entry_price"] == pytest.approx(4.21)
    assert opened[0]["entry"]["bids"] == book["bids"] and opened[0]["entry"]["late"] is False  # opened live, not read back after a restart
    paper.market.px["SMPL"] = [4.30, 4.29, 4.31]
    closed = paper.client.post("/api/agent/trader/close", headers=h, json={"symbol": "SMPL"})
    assert closed.status_code == 200, closed.text
    asyncio.run(watcher.run_pass(now=paper.market.now + 2))
    body = paper.client.get("/api/agent/trader/journal").json()
    assert body["open"] == [] and len(body["trades"]) == 1
    trade = body["trades"][0]
    assert trade["exit_reason"] == "manual" and trade["exit_price"] == pytest.approx(4.29)
    assert trade["pnl"] == pytest.approx(100 * (4.29 - 4.21) - trade["fees"])
    assert trade["exit"]["asks"] == book["asks"] and trade["shares"] == 100
    assert journal.path_for(body["day"]).exists()
    assert any(e["kind"] == "close" and "trade on SMPL closed" in e["text"] for e in seat.snapshot()["events"])


def test_a_guard_close_is_journaled_as_the_guard(paper, monkeypatch):
    import ibkr.depth as depth

    h = _seat(paper)
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    monkeypatch.setattr(depth, "current_book", lambda s: {"bids": [{"price": 4.18, "size": 900}], "asks": []})
    asyncio.run(watcher.run_pass(now=paper.market.now + 2))
    asyncio.run(watcher.run_pass(now=paper.market.now + 3))
    trade = paper.client.get("/api/agent/trader/journal").json()["trades"][0]
    assert trade["exit_reason"] == "guard" and "under entry" in trade["exit_detail"]


# -- restarts and a new session -----------------------------------------------------------------------------
def test_a_restart_keeps_the_seat_and_restarts_its_lease(paper):
    _seat(paper)
    paper.market.now += AGENT_LEASE_SEC + 60          # the backend was down longer than the lease
    seat.reset_for_tests()                            # a restart: read back from the file
    assert seat.holder() and seat.symbol() == "SMPL" and not seat.lapsed()
    assert seat.snapshot()["events"][-1]["kind"] == "resumed"


def test_a_new_session_picks_the_seat_up_in_one_call(paper):
    h = _seat(paper)
    refused = paper.client.post("/api/agent/trader/seat", headers=paper.key)
    assert refused.status_code == 409 and "take_over" in refused.json()["detail"]["error"]
    got = paper.client.post("/api/agent/trader/seat?take_over=true", headers=paper.key)
    assert got.status_code == 200, got.text
    assert got.json()["status"]["symbol"] == "SMPL"                                    # the stock is kept
    old = paper.client.post("/api/agent/trader/beat", headers=h)
    assert old.status_code == 403                                                      # the old token stops
    new = paper.client.post("/api/agent/trader/beat", headers={**paper.key, "X-Agent-Seat": got.json()["token"]})
    assert new.status_code == 200


# -- trading halts ------------------------------------------------------------------------------------------
@pytest.fixture
def halted(monkeypatch):
    """The scanner's halt source, by symbol (AIOK halted at 15.74 seconds after a resting buy, 2026-10-27)."""
    from ibkr import halt_status

    now: dict[str, bool | None] = {}
    monkeypatch.setattr(halt_status, "halted_now", lambda syms, now_=None, **kw: {s: now.get(s) for s in syms})
    return now


def test_an_entry_on_a_halted_stock_is_refused_and_said(paper, halted):
    h = _seat(paper)
    halted["SMPL"] = True
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.10, "stop": 4.00, "target": 4.60, "why": "x"})
    assert got.status_code == 409 and got.json()["detail"]["reason"] == "AGENT_HALTED"
    assert any(e["kind"] == "refused" and "halted" in e["text"] for e in seat.snapshot()["events"])
    halted["SMPL"] = None                                              # not known: never inferred, the entry goes
    ok = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.10, "stop": 4.00, "target": 4.60, "why": "x"})
    assert ok.status_code == 200, ok.text


def test_a_halt_cancels_claudes_resting_buy_and_breaks_but_keeps_a_held_stop(paper, halted):
    h = _seat(paper)
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.10, "stop": 4.00, "target": 4.60, "why": "rest"})
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "break", "symbol": "SMPL", "qty": 100, "trigger": 4.40, "top": 4.44, "stop": 4.20, "target": 4.90,
        "why": "over 4.40"})
    assert any(r["leg_role"] == "parent" for r in ledger.working()) and seat.breaks()
    halted["SMPL"] = True
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    assert not [r for r in ledger.working() if r["leg_role"] == "parent"] and not seat.breaks()
    texts = [e["text"] for e in seat.snapshot()["events"]]
    assert any("halted: Nova cancelled Claude's buy at 4.1" in t for t in texts)
    assert any("halted: Nova took back Claude's break at 4.4" in t for t in texts)


def test_the_guard_does_not_sell_into_a_halt(paper, halted, monkeypatch):
    import ibkr.depth as depth

    h = _seat(paper)
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    assert ledger.position("SMPL") == 100
    halted["SMPL"] = True
    monkeypatch.setattr(depth, "current_book", lambda s: {"bids": [{"price": 4.10, "size": 100}], "asks": []})
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    assert ledger.position("SMPL") == 100                              # the bid is 2.6% under entry: still held
    assert {r["leg_role"] for r in ledger.working()} == {"target", "stop"}
    halted["SMPL"] = False                                             # it trades again: the guard judges
    asyncio.run(watcher.run_pass(now=paper.market.now + 2))
    assert ledger.position("SMPL") == 0


# -- the LULD band ------------------------------------------------------------------------------------------
BAND = {"state": "bands", "upper": 4.40, "lower": 3.60, "exact": True}


def test_the_band_as_claude_reads_it_and_none_where_the_source_has_none():
    from agent_trader import bands

    got = bands.of("SMPL", 4.00, BAND)
    assert got["upper"] == 4.40 and got["pct_to_upper"] == pytest.approx(10.0)
    assert got["pct_to_lower"] == pytest.approx(10.0) and got["state"] == "bands"
    none = bands.of("SMPL", 4.00, {"state": "unknown", "upper": None, "lower": None})
    assert none["upper"] is None and none["pct_to_upper"] is None and none["state"] == "unknown"


def test_a_bid_on_the_upper_band_with_nothing_offered_under_it_is_at_the_limit():
    from agent_trader import bands

    pinned = {"bids": [{"price": 4.40, "size": 9_000}], "asks": [{"price": 4.45, "size": 100}]}
    assert bands.at_limit(pinned, BAND)
    assert not bands.at_limit({**pinned, "asks": [{"price": 4.40, "size": 100}]}, BAND)   # offered at the band
    assert not bands.at_limit({"bids": [{"price": 4.30, "size": 9_000}], "asks": []}, BAND)
    assert not bands.at_limit(pinned, {"state": "unknown", "upper": None})


def test_a_buy_near_the_upper_band_is_warned_never_refused(paper, monkeypatch):
    from luld import live

    monkeypatch.setattr(live, "view", lambda s, now=None: {**BAND, "upper": 4.27})
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 100, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    assert got.status_code == 200, got.text
    assert "upper LULD band 4.27" in got.json()["warnings"][0]
    from l2 import tape

    monkeypatch.setattr(tape, "get_trades_in_range", lambda *a, **k: [])
    look = paper.client.get("/api/agent/trader/look?symbol=SMPL").json()
    assert look["luld"]["upper"] == 4.27 and look["book"]["at_limit"] is False
    monkeypatch.setattr(live, "view", lambda s, now=None: {**BAND, "upper": 9.00})
    far = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "break", "symbol": "SMPL", "qty": 100, "trigger": 4.40, "top": 4.44, "stop": 4.20, "target": 4.90,
        "why": "x"})
    assert far.status_code == 200 and far.json()["warnings"] == []
