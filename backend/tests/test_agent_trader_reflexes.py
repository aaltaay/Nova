"""Claude's reflexes (ADR 068 decision 11): Level 2 / Time & Sales conditions Nova acts on within half a second, and a
break that sends only while buyers lead. Pure checks first, then end to end on the real Paper broker (the fixture of
``test_agent_trader``)."""
from __future__ import annotations

import asyncio

import pytest

from agent_trader import ledger, reflexes, seat, view, watcher
from tests.test_agent_trader import _fresh_seat, _seat, paper  # noqa: F401  (fixtures)

BOOK = {"bids": [{"price": 4.31, "size": 3000, "mm": "NSDQ"}, {"price": 4.31, "size": 1500, "mm": "ARCA"},
                 {"price": 4.30, "size": 2000, "mm": "NSDQ"}, {"price": 4.25, "size": 9000, "mm": "EDGX"}],
        "asks": [{"price": 4.32, "size": 1700, "mm": "NSDQ"}, {"price": 4.35, "size": 25000, "mm": "ARCA"}]}


def _print(ts, price, size, bid, ask):
    return {"ts": ts, "price": price, "size": size, "bid": bid, "ask": ask}


# -- pure ---------------------------------------------------------------------------------------------------
def test_a_reflex_must_say_what_it_watches_and_what_it_does():
    assert reflexes.shape_refusal({"kind": "bid_pulled", "action": "sell_all", "price": 4.3, "shares": 5000}) is None
    assert "needs price, shares" in reflexes.shape_refusal({"kind": "bid_pulled", "action": "sell_all", "price": 4.3})
    assert reflexes.shape_refusal({"kind": "vibes", "action": "sell_all"})
    assert reflexes.shape_refusal({"kind": "sellers", "action": "sell_all", "seconds": 90, "shares": 1, "ratio": 1})
    assert reflexes.text({"kind": "ask_wall", "action": "cancel_buy", "price": 4.4, "shares": 20000}) == \
        "Cancel my buy if a seller of 20,000+ shares shows at 4.4 or lower"


def test_the_book_adds_up_across_market_makers():
    assert reflexes.levels(BOOK, "bids")[4.31] == 4500
    assert reflexes.bid_depth(BOOK, 4.30) == 6500


def test_each_kind_fires_on_its_own_condition():
    row = {"kind": "bid_pulled", "action": "sell_all", "price": 4.30, "shares": 5000}
    assert reflexes.primes(row, BOOK)
    pulled = {"bids": [{"price": 4.31, "size": 1000}, {"price": 4.30, "size": 500}], "asks": []}
    assert reflexes.fired(row, book=pulled, prints=[], now=10, primed=False) is None      # never saw its size
    assert "fell to 1,500" in reflexes.fired(row, book=pulled, prints=[], now=10, primed=True)
    wall = {"kind": "ask_wall", "action": "sell_all", "price": 4.36, "shares": 20000}
    assert "25,000-share seller showed at 4.35" in reflexes.fired(wall, book=BOOK, prints=[], now=10, primed=False)
    tape = [_print(5, 4.30, 4000, 4.30, 4.31), _print(6, 4.31, 500, 4.30, 4.31), _print(1, 4.30, 99999, 4.30, 4.31)]
    sellers = {"kind": "sellers", "action": "sell_all", "seconds": 8, "shares": 3000, "ratio": 3}
    assert "4,000 shares hit the bid" in reflexes.fired(sellers, book=None, prints=tape, now=10, primed=False)
    below = {"kind": "last_below", "action": "sell_all", "price": 4.30, "created_at": 4.5}
    assert "printed 4.3" in reflexes.fired(below, book=None, prints=tape, now=10, primed=False)
    assert reflexes.fired({**below, "created_at": 9}, book=None, prints=tape, now=10, primed=False) is None


def test_a_confirm_wants_buyers_to_lead():
    tape = [_print(8, 4.40, 6000, 4.38, 4.40), _print(9, 4.38, 1000, 4.38, 4.40)]
    assert reflexes.confirmed({"seconds": 5, "shares": 5000, "ratio": 2}, tape, 10)[0]
    assert not reflexes.confirmed({"seconds": 5, "shares": 5000, "ratio": 7}, tape, 10)[0]
    assert reflexes.confirmed(None, [], 10) == (True, "")


# -- end to end on Paper ------------------------------------------------------------------------------------
@pytest.fixture
def market_feed(monkeypatch, paper):  # noqa: F811
    """The live book and Nova's tape archive for SMPL, as the test sets them."""
    import ibkr.depth as depth_mod
    from l2 import tape

    feed = {"book": None, "prints": []}
    monkeypatch.setattr(depth_mod, "current_book", lambda s: feed["book"])
    monkeypatch.setattr(tape, "get_trades_in_range",
                        lambda s, a, b: [p for p in feed["prints"] if a <= p["ts"] <= b])
    return feed


def _hold(paper, h, qty=300):  # noqa: F811
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": qty, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    assert got.status_code == 200, got.text
    assert ledger.position("SMPL") == qty


def test_a_pulled_bid_sells_claudes_shares_within_a_pass(paper, market_feed):  # noqa: F811
    h = _seat(paper)
    _hold(paper, h)
    armed = paper.client.post("/api/agent/trader/reflex", headers=h, json={
        "kind": "bid_pulled", "action": "sell_all", "price": 4.30, "shares": 5000, "why": "the 4.30 bid is the floor"})
    assert armed.status_code == 200, armed.text
    assert view.status()["reflexes"][0]["text"].startswith("Sell all my shares if the bids at 4.3")
    market_feed["book"] = BOOK
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))          # primed: 6,500 shares guard 4.30
    assert ledger.position("SMPL") == 300
    market_feed["book"] = {"bids": [{"price": 4.30, "size": 800}], "asks": BOOK["asks"]}
    asyncio.run(watcher.run_pass(now=paper.market.now + 1.5))
    assert ledger.position("SMPL") == 0 and not ledger.working() and not seat.reflexes()
    fired = [e for e in view.status()["events"] if e["kind"] == "reflex_fired"]
    assert fired and "fell to 800" in fired[0]["text"] and "sold 300 SMPL" in fired[0]["text"]


def test_an_ask_wall_calls_off_claudes_buy(paper, market_feed):  # noqa: F811
    h = _seat(paper)
    paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "break", "symbol": "SMPL", "qty": 400, "trigger": 4.30, "top": 4.34, "stop": 4.05, "target": 4.80,
        "why": "over 4.30"})
    paper.client.post("/api/agent/trader/reflex", headers=h, json={
        "kind": "ask_wall", "action": "cancel_buy", "price": 4.36, "shares": 20000, "why": "a big seller kills it"})
    market_feed["book"] = BOOK
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    assert not seat.breaks() and not seat.reflexes() and ledger.position("SMPL") == 0


def test_a_break_waits_for_buyers_then_sends(paper, market_feed):  # noqa: F811
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "break", "symbol": "SMPL", "qty": 400, "trigger": 4.30, "top": 4.34, "stop": 4.05, "target": 4.80,
        "confirm": {"seconds": 5, "shares": 3000, "ratio": 2}, "why": "only with buyers"})
    assert got.status_code == 200, got.text
    t0 = paper.market.now
    paper.market.px["SMPL"] = [4.31, 4.30, 4.32]
    paper.market.prints.append((t0 + 2, 4.31))
    market_feed["prints"] = [_print(t0 + 2, 4.30, 2000, 4.30, 4.31)]           # sellers, not buyers
    asyncio.run(watcher.run_pass(now=t0 + 3))
    assert len(seat.breaks()) == 1 and ledger.position("SMPL") == 0
    assert any(e["kind"] == "break_wait" for e in view.status()["events"])
    paper.market.prints.append((t0 + 4, 4.32))
    market_feed["prints"].append(_print(t0 + 4, 4.32, 5000, 4.31, 4.32))       # buyers lift the ask
    asyncio.run(watcher.run_pass(now=t0 + 5))
    assert not seat.breaks() and ledger.position("SMPL") == 400


def test_every_fill_is_said_once(paper, market_feed):  # noqa: F811
    h = _seat(paper)
    _hold(paper, h, qty=200)
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    asyncio.run(watcher.run_pass(now=paper.market.now + 2))
    said = [e["text"] for e in view.status()["events"] if e["kind"] == "fill"]
    assert said == ["Claude bought 200 SMPL at 4.21"]
