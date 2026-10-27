"""Nova's guard on Claude's open trade and the pop exit (ADR 068 decision 13, operator 2026-10-27).

The judge is tested on handed books and prints; the sells and the stop move end to end on the real Paper broker
(the seat suite's ``paper`` fixture: SMPL last 4.20, bid 4.19, ask 4.21, 10:30 ET).
"""
from __future__ import annotations

import asyncio

import pytest

from agent_trader import guard, ledger, seat, watcher
from agent_trader.constants_agent_trader import (
    AGENT_GUARD_BID_UNDER_ENTRY_PCT,
    AGENT_GUARD_SELLERS_MIN_SHARES,
    AGENT_POP_PCT_DEFAULT,
)
from practice import matcher
from tests.test_agent_trader import _fresh_seat, _seat, paper  # noqa: F401 -- fixtures

NOW = 1_000.0


@pytest.fixture(autouse=True)
def _fresh_guard():
    guard.reset_for_tests()
    yield
    guard.reset_for_tests()


def _book(bids: list[tuple[float, float]], asks: list[tuple[float, float]] | None = None, **extra) -> dict:
    return {"bids": [{"price": p, "size": s} for p, s in bids],
            "asks": [{"price": p, "size": s} for p, s in (asks or [(4.30, 500)])], **extra}


def _print(ago: float, px: float, size: float, bid: float = 4.19, ask: float = 4.21) -> dict:
    return {"ts": NOW - ago, "price": px, "size": size, "bid": bid, "ask": ask}


ENTRY = {"entry": 4.20, "stack": 9_000.0}
FIVE = [(4.19, 2_000), (4.18, 2_000), (4.17, 2_000), (4.16, 2_000), (4.15, 1_000), (4.10, 50_000)]


# -- the judge ----------------------------------------------------------------------------------------------
def test_quiet_tape_and_a_full_book_do_not_sell():
    assert guard.judge(ENTRY, book=_book(FIVE), prints=[_print(1, 4.21, 400)], now=NOW) is None


def test_sellers_two_to_one_on_1500_shares_in_five_seconds_sell():
    prints = [_print(1, 4.19, AGENT_GUARD_SELLERS_MIN_SHARES), _print(2, 4.21, 700)]
    assert "sellers lead" in guard.judge(ENTRY, book=_book(FIVE), prints=prints, now=NOW)
    old = [_print(6, 4.19, 5_000)]                                      # outside the 5 s
    assert guard.judge(ENTRY, book=_book(FIVE), prints=old, now=NOW) is None
    small = [_print(1, 4.19, AGENT_GUARD_SELLERS_MIN_SHARES - 1)]
    assert guard.judge(ENTRY, book=_book(FIVE), prints=small, now=NOW) is None


def test_the_top_five_bids_under_a_third_of_entry_sell_and_a_level_1_stand_in_is_not_judged():
    assert guard.bid_stack(_book(FIVE)) == 9_000                        # the 6th price is not counted
    thin = _book([(4.19, 900), (4.18, 900), (4.17, 900)])
    assert "the bids left" in guard.judge(ENTRY, book=thin, prints=[], now=NOW)
    assert guard.judge(ENTRY, book={**thin, "l1_fallback": True}, prints=[], now=NOW) is None


def test_the_bid_point_four_percent_under_entry_sells():
    under = round(4.20 * (1 - AGENT_GUARD_BID_UNDER_ENTRY_PCT / 100), 4)
    low = _book([(under, 3_000), (4.18, 3_000), (4.17, 3_000)])
    assert "under entry" in guard.judge(ENTRY, book=low, prints=[], now=NOW)
    assert guard.judge(ENTRY, book=None, prints=[], now=NOW, l1_bid=under) is not None   # Level 1's bid when no book
    assert guard.judge(ENTRY, book=None, prints=[], now=NOW, l1_bid=4.19) is None


def test_the_entry_is_the_average_of_buys_since_the_position_was_last_flat():
    fills = [{"symbol": "SMPL", "side": "BUY", "filled_qty": 100, "avg_fill_price": 3.00, "fill_ts": 1},
             {"symbol": "SMPL", "side": "SELL", "filled_qty": 100, "avg_fill_price": 3.10, "fill_ts": 2},
             {"symbol": "SMPL", "side": "BUY", "filled_qty": 100, "avg_fill_price": 4.00, "fill_ts": 3},
             {"symbol": "SMPL", "side": "BUY", "filled_qty": 300, "avg_fill_price": 4.40, "fill_ts": 4},
             {"symbol": "SMPL", "side": "SELL", "filled_qty": 200, "avg_fill_price": 4.50, "fill_ts": 5}]
    entry, opened = guard.entry_of(fills, "smpl")
    assert entry == pytest.approx(4.30) and opened == 3
    assert guard.entry_of(fills[:2], "SMPL") == (None, 1.0)


# -- end to end on Paper ------------------------------------------------------------------------------------
def test_the_guard_sells_claudes_shares_and_says_why(paper, monkeypatch):
    import ibkr.depth as depth

    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 500, "entry": 4.25, "stop": 4.00, "target": 4.80, "why": "go"})
    assert got.status_code == 200 and ledger.position("SMPL") == 500   # filled at the 4.21 ask
    monkeypatch.setattr(depth, "current_book", lambda s: _book([(4.20, 3_000), (4.19, 3_000)]))
    asyncio.run(watcher.run_pass(now=paper.market.now + 1))
    assert ledger.position("SMPL") == 500                               # 4.20 is 0.24% under the 4.21 entry
    monkeypatch.setattr(depth, "current_book", lambda s: _book([(4.19, 3_000), (4.18, 3_000)]))
    asyncio.run(watcher.run_pass(now=paper.market.now + 2))
    assert ledger.position("SMPL") == 0 and not ledger.working()
    fired = [e for e in seat.snapshot()["events"] if e["kind"] == "reflex_fired"]
    assert fired and "Nova's guard on SMPL" in fired[-1]["text"] and "under entry" in fired[-1]["text"]


def test_the_pop_exit_sells_half_at_the_pop_then_moves_the_stop_to_entry(paper):
    h = _seat(paper)
    got = paper.client.post("/api/agent/trader/order", headers=h, json={
        "kind": "limit", "symbol": "SMPL", "qty": 501, "entry": 4.25, "stop": 4.00, "target": 4.80,
        "exit": "pop", "why": "go"})
    assert got.status_code == 200, got.text
    legs = {r["leg_role"]: r for r in ledger.working()}
    pop = round(4.25 * (1 + AGENT_POP_PCT_DEFAULT / 100), 2)
    assert {"target", "target2", "stop"} <= set(legs)
    assert float(legs["target"]["limit_price"]) == pop and float(legs["target"]["qty"]) == 250
    assert seat.exits() == {"SMPL": {"mode": "pop", "pop_pct": AGENT_POP_PCT_DEFAULT}}
    paper.market.px["SMPL"] = [4.33, 4.32, 4.34]
    paper.market.prints.append((paper.market.now + 1, 4.33))
    asyncio.run(matcher.pass_once(paper.broker, now=paper.market.now + 2))
    assert ledger.position("SMPL") == 251                               # the first half sold at the pop
    asyncio.run(watcher.run_pass(now=paper.market.now + 3))
    stop = next(r for r in ledger.working() if r["leg_role"] == "stop")
    assert float(stop["stop_price"]) == 4.21                            # Claude's entry (the 4.21 ask)
    assert any(e["kind"] == "stop" and "entry 4.21" in e["text"] for e in seat.snapshot()["events"])


@pytest.mark.parametrize("change, words", [({"qty": 1}, "2 shares"), ({"target": 4.30}, "must be above")])
def test_a_pop_exit_that_cannot_sell_half_is_refused_in_words(paper, change, words):
    h = _seat(paper)
    body = {"kind": "limit", "symbol": "SMPL", "qty": 500, "entry": 4.25, "stop": 4.00, "target": 4.80,
            "exit": "pop", "why": "go", **change}
    got = paper.client.post("/api/agent/trader/order", headers=h, json=body)
    assert got.status_code == 409 and words in got.json()["detail"]["error"]
