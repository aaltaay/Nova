"""The three traders' books inside one account (ADR 069, ADR 072): the split, each holder's own cost, the rules
that keep each trader's stock its own, the rows your controls size from, and the books on the wire."""
from __future__ import annotations

import pytest

from constants_owners import (
    OWNERS_BUDGET_CODE,
    OWNERS_TRADER_ON_CODE,
    OWNERS_TRADERS_STOCK_CODE,
)
from owners import books, rules
from owners.split import split_fill
from practice import history
from practice.fees import Fees
from practice.ledger import Ledger

T0 = 1_790_000_000.0
FEE = Fees(commission=1.0)


def _ledger(split: bool = True) -> Ledger:
    ledger = Ledger(100_000, created_ts=T0, split_owners=split)
    ledger.venue = "paper"
    return ledger


@pytest.fixture(autouse=True)
def _ai_traders_on():
    """Claude and the brain switched On, as the operator does before they trade (ADR 072)."""
    from traders import switches

    for trader in ("claude", "brain"):
        switches.set_switch(trader, True, "test")


_ids = iter(range(1, 10_000))


def place(ledger: Ledger, symbol: str, side: str, qty: float, *, source: str = "manual", origin: str | None = None,
          limit: float | None = None) -> int:
    oid = next(_ids)
    ledger.place({"order_id": oid, "symbol": symbol, "side": side, "qty": qty, "order_origin": origin,
                  "limit_price": limit, "effect": "opens"}, ts=T0 + oid, source=source)
    return oid


def trade(ledger: Ledger, symbol: str, side: str, qty: float, price: float, **kw) -> None:
    oid = place(ledger, symbol, side, qty, **kw)
    ledger.fill(oid, ts=T0 + 0.5 + oid, price=price, basis="test", fees=FEE)


LT = {"source": "bot", "origin": "live_trader"}
LT_CLOSE = {"source": "flatten", "origin": "live_trader"}
CLAUDE = {"source": "bot", "origin": "claude"}
BRAIN = {"source": "bot", "origin": "brain"}


# ---------------------------------------------------------------- the split
def test_a_fill_closes_its_own_shares_first_and_opens_the_rest_for_its_sender() -> None:
    assert split_fill({"you": 100, "live_trader": 50}, 30, buy=False, sender="you") == [("you", 30, True)]
    assert split_fill({"you": 10, "live_trader": 50}, 30, buy=False, sender="live_trader") == [("live_trader", 30, True)]
    assert split_fill({}, 20, buy=True, sender="claude") == [("claude", 20, False)]


def test_novas_own_close_takes_from_each_book_in_proportion() -> None:
    parts = dict((h, n) for h, n, _ in split_fill({"you": 100, "live_trader": 50}, 150, buy=False, sender=None))
    assert parts == {"you": 100, "live_trader": 50}


def test_your_close_into_the_bots_book_takes_auto_entrys_shares_first() -> None:
    held = {"auto_entry": 10, "live_trader": 51}
    assert split_fill(held, 10, buy=False, sender="you") == [("auto_entry", 10, True)]


# ------------------------------------------------------------ each its cost
def test_each_holder_is_booked_at_its_own_cost_and_the_two_add_up() -> None:
    ledger = _ledger()
    trade(ledger, "ABC", "BUY", 100, 10.0)
    trade(ledger, "ABC", "BUY", 100, 12.0, **LT)
    trade(ledger, "ABC", "SELL", 100, 11.0)                      # you sell yours
    assert ledger.owners.realized["you"] == pytest.approx(100 - 2.0)    # $100 made, two $1 commissions
    assert ledger.owners.realized["live_trader"] == pytest.approx(-1.0)
    assert (ledger.held_qty("ABC"), ledger.avg_cost("ABC")) == (100.0, 12.0)   # the bot's 100 at its own 12
    assert ledger.realized == pytest.approx(sum(ledger.owners.realized.values()))


def test_a_one_pile_ledger_books_as_before() -> None:
    split, pile = _ledger(), _ledger(split=False)
    for ledger in (split, pile):
        trade(ledger, "ABC", "BUY", 100, 10.0)
        trade(ledger, "ABC", "BUY", 50, 10.5)
        trade(ledger, "ABC", "SELL", 120, 10.75)
    assert (split.held_qty("ABC"), split.avg_cost("ABC"), split.realized, split.cash) == \
           (pile.held_qty("ABC"), pile.avg_cost("ABC"), pile.realized, pile.cash)
    assert pile.owners is None


# ------------------------------------------------------------------- rules
def _refusal(ledger: Ledger, side: str, qty: float, **kw):
    order = {"source": kw.pop("source", "manual"), "origin": kw.pop("origin", None)}
    from owners.whose import holder_of_order

    return rules.refusal(ledger, symbol="SPCX", side=side, qty=qty, short_entry=kw.pop("short_entry", False),
                         holder=holder_of_order(order["source"], order["origin"]), **kw)


def test_a_traders_stock_is_its_own() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 200, 4.25, **BRAIN)
    assert rules.stock_of(ledger, "SPCX") == "brain"
    assert _refusal(ledger, "BUY", 50, **CLAUDE) == (
        "Claude skipped SPCX: it is the brain's, and nobody adds to another trader's stock.", OWNERS_TRADERS_STOCK_CODE)
    assert _refusal(ledger, "BUY", 50, **BRAIN) is None           # the brain adds to its own
    yours = _ledger()
    place(yours, "SPCX", "BUY", 100, limit=4.0)                  # your entry rests: the stock is yours
    assert rules.stock_of(yours, "SPCX") == "you"
    assert _refusal(yours, "BUY", 50, **CLAUDE)[1] == OWNERS_TRADERS_STOCK_CODE


def test_you_leave_an_on_traders_stock_alone_until_you_switch_it_off() -> None:
    from traders import switches

    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 51, 140.0, **CLAUDE)
    for side in ("BUY", "SELL"):
        assert _refusal(ledger, side, 51) == ("SPCX is Claude's. Switch Claude off to close it yourself.",
                                              OWNERS_TRADER_ON_CODE)
    switches.set_switch("claude", False, "test")                 # Off: its shares read as handed to you
    assert rules.handed_from(ledger, "SPCX") == "claude"
    assert _refusal(ledger, "SELL", 51) is None                  # you close it
    assert _refusal(ledger, "BUY", 10) == ("SPCX was handed to you by Claude: you close it, never add to it.",
                                           OWNERS_TRADERS_STOCK_CODE)
    assert _refusal(ledger, "SELL", 51, **CLAUDE)[1] == OWNERS_TRADERS_STOCK_CODE   # nor may Claude act there


def test_a_handed_position_stays_handed_when_the_trader_comes_back_on() -> None:
    from traders import handed, switches

    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 51, 140.0, **CLAUDE)
    handed.hand("paper", "claude", ["SPCX"], T0)
    switches.set_switch("claude", True, "test")
    assert rules.handed_from(ledger, "SPCX") == "claude"
    assert _refusal(ledger, "SELL", 51) is None
    trade(ledger, "SPCX", "SELL", 51, 141.0)                      # you close it: the mark ends
    assert handed.active("paper", ledger) == {} and handed.entries() == []


def test_your_sell_closes_your_shares_and_those_handed_to_you() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 100, 141.0)
    trade(ledger, "AAA", "BUY", 1, 1.0, **CLAUDE)                 # Claude elsewhere
    assert _refusal(ledger, "SELL", 100) is None
    earlier = _ledger()
    trade(earlier, "SPCX", "BUY", 10, 140.0, source="bot", origin="auto_entry")
    trade(earlier, "SPCX", "BUY", 100, 140.0)
    assert rules.handed_from(earlier, "SPCX") == "earlier_bots"   # a retired bot's shares are handed to you
    assert _refusal(earlier, "SELL", 110) is None
    trade(earlier, "SPCX", "SELL", 110, 141.0)
    assert earlier.held_qty("SPCX") == 0


def test_nobody_adds_to_a_stock_another_holds_either_way() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "SELL", 51, 140.0, **BRAIN)             # the brain is short 51
    assert _refusal(ledger, "BUY", 100, **CLAUDE)[1] == OWNERS_TRADERS_STOCK_CODE
    other = _ledger()
    trade(other, "SPCX", "SELL", 51, 140.0, **LT)                 # a retired bot's short, handed to you
    reason, code = _refusal(other, "SELL", 10, short_entry=True)
    assert code == OWNERS_TRADERS_STOCK_CODE and "never add to it" in reason


def test_each_ai_trader_has_its_own_budget() -> None:
    ledger = _ledger()
    reason, code = _refusal(ledger, "BUY", 100, **BRAIN, price=25.0, budget_usd=25_000, used_usd=23_400)
    assert code == OWNERS_BUDGET_CODE
    assert reason == "The brain skipped SPCX: its $25,000 would be passed ($23,400 held + $2,500)."
    assert _refusal(ledger, "BUY", 60, **BRAIN, price=25.0, budget_usd=25_000, used_usd=23_400) is None
    assert _refusal(ledger, "BUY", 10_000, price=25.0, budget_usd=25_000, used_usd=23_400) is None  # yours: none


def test_novas_own_closes_and_a_ledger_without_books_are_never_refused_here() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 51, 140.0, **CLAUDE)
    assert _refusal(ledger, "SELL", 51, source="flatten") is None   # KILL / the day cover: no holder
    pile = _ledger(split=False)
    trade(pile, "SPCX", "BUY", 51, 140.0, **CLAUDE)
    assert _refusal(pile, "SELL", 51) is None


# -------------------------------------------------------------- the wire
def test_your_controls_see_your_and_handed_shares_and_the_books_add_up_to_the_account() -> None:
    from traders import switches

    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 4, 140.0, **LT)
    trade(ledger, "SPCX", "BUY", 100, 141.0)
    trade(ledger, "TSLA", "BUY", 6, 400.0, **CLAUDE)
    trade(ledger, "XLAB", "BUY", 20, 4.0, **BRAIN)
    rows = {r["symbol"]: r for r in books.yours(ledger.position_rows(by_owner=True))}
    assert list(rows) == ["SPCX"]                                 # TSLA is Claude's, XLAB the brain's
    assert (rows["SPCX"]["qty"], rows["SPCX"]["handed_qty"], rows["SPCX"]["handed_from"]) == (104.0, 4.0,
                                                                                               "earlier_bots")
    switches.set_switch("brain", False, "test")
    rows = {r["symbol"]: r for r in books.yours(ledger.position_rows(by_owner=True))}
    assert rows["XLAB"]["handed_from"] == "brain" and rows["XLAB"]["qty"] == 20
    out = books.books(ledger, account_day_pnl=round(ledger.day_pnl(), 2))
    assert list(out) == ["you", "claude", "brain", "earlier_bots"]
    assert (out["you"]["fills_today"], out["claude"]["fills_today"], out["brain"]["fills_today"]) == (1, 1, 1)
    assert sum(b["day_pnl"] for b in out.values()) == pytest.approx(round(ledger.day_pnl(), 2), abs=0.005)
    assert set(out["earlier_bots"]["by_bot"]) == {"live_trader"}
    assert out["claude"]["budget_usd"] == 25_000 and out["claude"]["budget_used_usd"] == pytest.approx(2_400)


def test_the_history_splits_every_fill_and_day_and_still_sums_to_the_account() -> None:
    ledger = _ledger()
    trade(ledger, "ABC", "BUY", 100, 10.0)
    trade(ledger, "ABC", "BUY", 100, 12.0, **LT)
    trade(ledger, "ABC", "SELL", 100, 11.0)
    trade(ledger, "ABC", "SELL", 100, 13.0, **LT_CLOSE)
    trade(ledger, "XYZ", "BUY", 10, 5.0, **CLAUDE)
    out = history.build(ledger, venue="paper", range_key="ALL", now_ts=T0 + 3600)
    assert out["schema_version"] == 3
    assert [(f["owner"], f["bot"]) for f in out["fills"]] == [("you", None), ("earlier_bots", "live_trader")] * 2 + [
        ("claude", None)]
    (day,) = out["daily"]
    assert day["you"]["realized"] == pytest.approx(98.0) and day["earlier_bots"]["realized"] == pytest.approx(98.0)
    assert day["claude"]["realized"] == pytest.approx(-1.0) and day["brain"]["fills"] == 0
    assert sum(day[b]["realized"] for b in ("you", "claude", "brain", "earlier_bots")) == pytest.approx(day["realized"])
    assert {(r["owner"], r["bot"]) for r in out["by_owner"]} == {("you", None), ("earlier_bots", "live_trader"),
                                                                ("claude", None)}
    last = out["equity"][-1]
    total = sum(last[f"{b}_pnl"] for b in ("you", "claude", "brain", "earlier_bots"))
    assert total == pytest.approx(last["net_liquidation"] - 100_000, abs=1e-3)


def test_your_close_of_handed_shares_is_booked_on_the_traders_book_closed_by_you() -> None:
    from traders import switches

    ledger = _ledger()
    trade(ledger, "XLAB", "BUY", 200, 4.0, **BRAIN)
    switches.set_switch("brain", False, "test")
    trade(ledger, "XLAB", "SELL", 200, 4.5)                       # you close what the brain handed you
    fill = history.build(ledger, venue="paper", range_key="ALL", now_ts=T0 + 3600)["fills"][-1]
    assert fill["owner"] == "you" and fill["closed_by"] == "you"
    assert [(p["owner"], p["closed_by"]) for p in fill["parts"]] == [("brain", "you")]
    assert ledger.owners.realized["brain"] == pytest.approx(100 - 2.0)   # its gain, its book


class _Quote:
    def __init__(self) -> None:
        from sim.fill_model import Reference

        self.ref = Reference(40.0, 39.98, 40.02, live=True)

    def reference(self, symbol: str):
        return self.ref

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return T0 + 10_000


def test_an_ai_traders_budget_holds_through_a_reprice_and_at_the_fill() -> None:
    from practice import order_rules
    from practice.broker import PracticeBroker

    broker = PracticeBroker(_Quote(), _ledger(), "NOVA-PAPER", venue="paper")
    placed = broker.place("SPCX", "BUY", 1000, "LMT", limit_price=10.0, source="bot", origin="claude")
    assert placed["ok"] and broker.ledger.working_row(placed["order_id"])  # $10,000 of $25,000: it rests
    refused = broker.replace(placed["order_id"], limit_price=50.0)
    assert refused["ok"] is False and refused["reason_code"] == OWNERS_BUDGET_CODE
    assert "its $25,000 would be passed ($0 held + $50,000)" in refused["error"]
    assert broker.replace(placed["order_id"], limit_price=9.5)["ok"] is True   # cheaper is always fine
    row = broker.ledger.working_row(placed["order_id"])
    reason, code = order_rules.fill_refusal(broker.ledger, row, 50.0)
    assert code == OWNERS_BUDGET_CODE and reason.endswith("This order was cancelled at its fill.")
    assert order_rules.fill_refusal(broker.ledger, row, 9.5) is None


def test_a_waiting_short_bracket_stop_is_never_charged_to_the_budget() -> None:
    """PR #1270 review: before a short entry fills, its BUY stop still only ever covers -- moving it up is never a
    new entry against a trader's budget."""
    from practice.broker import PracticeBroker

    broker = PracticeBroker(_Quote(), _ledger(), "NOVA-PAPER", venue="paper")
    placed = broker.place_bracket("SPCX", "SELL", 400, 45.0, None, 47.0, short_entry=True, source="bot",
                                  origin="brain")
    assert placed["ok"], placed                                   # $18,000 short entry rests over the 40.02 ask
    moved = broker.replace(placed["stop_order_id"], stop_price=48.0)
    assert moved["ok"] is True, moved
    assert broker.ledger.working_row(placed["stop_order_id"])["stop_price"] == 48.0
