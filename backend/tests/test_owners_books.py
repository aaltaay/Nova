"""Your book and the bots' book inside one Paper account (ADR 069): the split, each holder's own cost, Paper's
rules, the rows your controls size from, and the books on the wire."""
from __future__ import annotations

import pytest

from constants_owners import (
    OWNERS_BOT_STAYS_OUT_CODE,
    OWNERS_BOTS_BUDGET_CODE,
    OWNERS_NOT_YOURS_CODE,
    OWNERS_OTHER_SIDE_CODE,
)
from owners import books, rules
from owners.split import split_fill
from practice import history
from practice.fees import Fees
from practice.ledger import Ledger

T0 = 1_790_000_000.0
FEE = Fees(commission=1.0)


def _ledger(split: bool = True) -> Ledger:
    return Ledger(100_000, created_ts=T0, split_owners=split)


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


def test_your_sell_closes_only_your_shares() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 51, 140.0, **LT)
    reason, code = _refusal(ledger, "SELL", 51)
    assert code == OWNERS_NOT_YOURS_CODE
    assert reason == "You hold no SPCX; the 51 are the Live Trader's. Your Sell closes only your shares."
    trade(ledger, "SPCX", "BUY", 100, 141.0)
    assert _refusal(ledger, "SELL", 100) is None
    assert _refusal(ledger, "SELL", 101)[1] == OWNERS_NOT_YOURS_CODE


def test_nobody_holds_the_other_side() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "SELL", 51, 140.0, **LT)               # the bot is short 51
    reason, code = _refusal(ledger, "BUY", 100)
    assert code == OWNERS_OTHER_SIDE_CODE
    assert reason == ("Buy SPCX refused: the Live Trader is short 51. One account can't be long and short the "
                      "same stock.")


def test_a_bot_stays_out_of_a_stock_you_hold_or_have_an_order_on_but_may_add_to_its_own() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 100, 140.0)
    assert _refusal(ledger, "BUY", 4, **LT) == ("The Live Trader skipped SPCX: you hold it.", OWNERS_BOT_STAYS_OUT_CODE)
    other = _ledger()
    place(other, "SPCX", "BUY", 100, limit=139.0)               # your buy rests
    assert _refusal(other, "BUY", 4, **LT)[1] == OWNERS_BOT_STAYS_OUT_CODE
    joined = _ledger()
    trade(joined, "SPCX", "BUY", 4, 140.0, **LT)
    trade(joined, "SPCX", "BUY", 100, 140.5)                     # you join it the same way
    assert _refusal(joined, "BUY", 4, **LT) is None              # the bot's add goes on


def test_the_bots_budget_counts_every_bot_together() -> None:
    ledger = _ledger()
    reason, code = _refusal(ledger, "BUY", 100, **LT, price=25.0, budget_usd=25_000, used_usd=23_400)
    assert code == OWNERS_BOTS_BUDGET_CODE
    assert reason == "The Live Trader skipped SPCX: the bots' $25,000 would be passed ($23,400 held + $2,500)."
    assert _refusal(ledger, "BUY", 60, **LT, price=25.0, budget_usd=25_000, used_usd=23_400) is None


def test_you_may_sell_auto_entrys_shares_and_the_bots_close_takes_only_theirs() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 10, 140.0, source="bot", origin="auto_entry")
    trade(ledger, "SPCX", "BUY", 100, 140.0)
    assert _refusal(ledger, "SELL", 110) is None                 # yours and Auto-entry's
    trade(ledger, "SPCX", "SELL", 110, 141.0)
    assert ledger.held_qty("SPCX") == 0
    bots = _ledger()
    trade(bots, "SPCX", "BUY", 51, 140.0, **LT)
    trade(bots, "SPCX", "BUY", 100, 140.0)
    assert _refusal(bots, "SELL", 51, source="flatten", origin="close_bots") is None
    assert _refusal(bots, "SELL", 52, source="flatten", origin="close_bots")[1] == OWNERS_NOT_YOURS_CODE


def test_novas_own_closes_and_sims_one_pile_are_never_refused_here() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 51, 140.0, **LT)
    assert _refusal(ledger, "SELL", 51, source="flatten") is None   # KILL / the day cover: no holder
    pile = _ledger(split=False)
    trade(pile, "SPCX", "BUY", 51, 140.0, **LT)
    assert _refusal(pile, "SELL", 51) is None


# -------------------------------------------------------------- the wire
def test_your_controls_see_your_shares_and_the_books_add_up_to_the_account() -> None:
    ledger = _ledger()
    trade(ledger, "SPCX", "BUY", 4, 140.0, **LT)
    trade(ledger, "SPCX", "BUY", 100, 141.0)
    trade(ledger, "TSLA", "BUY", 6, 400.0, **LT)
    rows = {r["symbol"]: r for r in books.yours(ledger.position_rows(by_owner=True))}
    assert list(rows) == ["SPCX"]                                 # TSLA is only the bot's
    assert (rows["SPCX"]["qty"], rows["SPCX"]["account_qty"], rows["SPCX"]["avg_cost"]) == (100.0, 104.0, 141.0)
    out = books.books(ledger, account_day_pnl=round(ledger.day_pnl(), 2), budget_usd=25_000, used_usd=0.0)
    assert out["you"]["fills_today"] == 1 and out["bots"]["fills_today"] == 2
    assert out["you"]["day_pnl"] + out["bots"]["day_pnl"] == pytest.approx(round(ledger.day_pnl(), 2), abs=0.005)
    assert set(out["bots"]["by_bot"]) == {"live_trader"}


def test_the_history_splits_every_fill_and_day_and_still_sums_to_the_account() -> None:
    ledger = _ledger()
    trade(ledger, "ABC", "BUY", 100, 10.0)
    trade(ledger, "ABC", "BUY", 100, 12.0, **LT)
    trade(ledger, "ABC", "SELL", 100, 11.0)
    trade(ledger, "ABC", "SELL", 100, 13.0, **LT_CLOSE)
    out = history.build(ledger, venue="paper", range_key="ALL", now_ts=T0 + 3600)
    assert [(f["owner"], f["bot"]) for f in out["fills"]] == [("you", None), ("bots", "live_trader")] * 2
    (day,) = out["daily"]
    assert day["you"]["realized"] == pytest.approx(98.0) and day["bots"]["realized"] == pytest.approx(98.0)
    assert day["you"]["realized"] + day["bots"]["realized"] == pytest.approx(day["realized"])
    assert {(r["owner"], r["bot"]) for r in out["by_owner"]} == {("you", None), ("bots", "live_trader")}
    last = out["equity"][-1]
    assert last["you_pnl"] + last["bots_pnl"] == pytest.approx(last["net_liquidation"] - 100_000, abs=1e-3)
