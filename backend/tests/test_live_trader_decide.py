"""The Live Trader bot's decision core (ADR 055): every rule of the mirror, one answer after another. Pure.

Each test drives ``decide`` with a sequence of feed answers (built here, made-up hosts and tickers) and fake
market reads, carrying the snapshot and the bot's book between passes as the watcher does.
"""
from __future__ import annotations

import pytest

from bot.live_trader import feed_rows, rules
from bot.live_trader.constants_live_trader import (
    LT_ADD_IMPLAUSIBLE,
    LT_ADDS_DONE,
    LT_AFTER_SELL_ALL,
    LT_AGAINST,
    LT_ALLOWANCE,
    LT_ALREADY_OPEN,
    LT_ASK_EXPIRED,
    LT_ASK_SKIPPED,
    LT_BLANK_BAR,
    LT_BLANK_HOLD_SEC,
    LT_BOT_OFF,
    LT_CAP_UNKNOWN,
    LT_FEED_BEHIND,
    LT_MISREAD,
    LT_NO_CLOCK,
    LT_NO_QUOTE,
    LT_OTHER_HOST,
    LT_RETURN_HOLD_SEC,
    LT_RETURN_SWITCH,
    LT_ROW_UNREAD,
    LT_SHORT_HOURS,
    LT_SHORTS_OFF,
    LT_SMALL_CAP,
    LT_TICKER_UNSETTLED,
)
from bot.live_trader.decide import decide

NOW = 1_790_000_000.0
HOST, OTHER = "TRADER1", "TRADER2"


def row(symbol="XYZ", *, host=HOST, side="long", price=100.0, entry_ts=NOW - 3, status="open", known=True,
        adds=(), exit_ts=None, ticker=None, left_bar=False):
    return {"id": f"{host}|{side}|{symbol}|{entry_ts:.0f}", "host": host, "side": side, "symbol": symbol,
            "status": status, "price": price, "entry_price": price, "entry_ts": entry_ts, "known": known,
            "adds": [dict(a) for a in adds], "exit_ts": exit_ts, "left_bar": left_bar, "ticker": ticker}


def answer(hosts=None, *, left=None, feed_now=None, age=1.0, behind=2.0, visible=True, live=True, state="ok",
           bars=None):
    """``bars``: each host's bar as the feed confirmed it (``["side:SYMBOL"]``; absent: the feed sends none)."""
    hosts = {HOST: []} if hosts is None else hosts
    return {"state": state, "error": None if state == "ok" else "could not connect", "date": "2026-10-15",
            "feed_now": NOW if feed_now is None else feed_now, "read_age_sec": age, "behind_sec": behind,
            "live": live, "bar_visible": visible, "order": list(hosts),
            "hosts": {n: {"left_ts": (left or {}).get(n), "rows": rows, "bar": (bars or {}).get(n)}
                      for n, rows in hosts.items()}}


def settings(**over):
    out = {"key": True, "entry": "nova", "exit": "nova", "step_usd": 500.0, "adds": 2, "allowance_usd": 2500.0,
           "sides": "both", "short_stop_pct": 5.0, "take_open": True}
    out.update(over)
    return out


QUOTE = {"last": 100.0, "bid": 99.98, "ask": 100.02, "fresh": True}


class World:
    """The watcher's side of the loop: the snapshot, the book, the market, applied between passes."""

    def __init__(self, **st):
        self.snap = None
        self.book: dict[str, dict] = {}
        self.now = NOW
        self.st = {HOST: settings(**st), OTHER: settings()}
        self.quotes = {"XYZ": dict(QUOTE)}
        self.caps: dict[str, object] = {}
        self.held: dict[tuple[str, str], float] = {}
        self.can = {"ok": True, "code": None, "why": None}
        self.sell_all_ts = None
        self.requests: dict = {}
        self.answers: dict = {}
        self.short_closed = None
        self.no_reentry: set = set()

    def ctx(self):
        return {"now": self.now, "settings": lambda n: self.st.get(n, settings(key=False)), "can_open": self.can,
                "sell_all_ts": self.sell_all_ts, "requests": self.requests, "quote": self.quotes.get,
                "cap": lambda s: self.caps.get(s, 50e9), "held": lambda s, side: self.held.get((s, side), 0.0),
                "short_closed": lambda now: self.short_closed, "answers": self.answers,
                "no_reentry": self.no_reentry}

    def run(self, ans, *, fill=True):
        out = decide(self.snap, ans, self.book, self.ctx())
        self.snap = out["snapshot"]
        self.answers = {}
        self.requests = {}
        for a in out["actions"]:
            if a["kind"] == "step" and fill:
                pos = self.book.get(a["pos_id"])
                if pos is None:
                    pos = self.book[a["pos_id"]] = {"id": a["pos_id"], "host": a["host"], "row_id": a["row_id"],
                                                    "symbol": a["symbol"], "side": a["side"], "qty": 0.0,
                                                    "cost_usd": 0.0, "steps": 0, "adds_followed": 0,
                                                    "opened_ts": self.now, "state": "open", "order": None}
                pos["qty"] += a["qty"]
                pos["cost_usd"] += a["qty"] * a["limit"]
                pos["steps"] += 1
                if a["step"] == "add":
                    pos["adds_followed"] += 1
            elif a["kind"] == "close":
                self.book.pop(a["pos_id"], None)
            elif a["kind"] == "rekey":
                self.book[a["pos_id"]]["row_id"] = a["row_id"]
        return out

    def at(self, sec):
        self.now = NOW + sec
        return self


def kinds(out, kind=None):
    acts = out["actions"]
    return [a for a in acts if kind is None or a["kind"] == kind]


def watching(w, *rows_now, **kw):
    """Two passes: an empty bar (the watch begins), then ``rows_now`` -- each a fresh entry, not already open."""
    w.run(answer())
    return w.at(kw.pop("after", 2)).run(answer({HOST: list(rows_now)}, feed_now=w.now, **kw))


# -- a position appears: one step ---------------------------------------------------------------------
def test_a_new_position_is_one_step_at_the_ask_plus_two_cents():
    w = World()
    out = watching(w, row(entry_ts=NOW))
    (step,) = kinds(out, "step")
    assert step["step"] == "entry" and step["side"] == "long" and step["symbol"] == "XYZ"
    assert step["limit"] == pytest.approx(100.04) and step["qty"] == 4          # $500 / 100.04, rounded down
    assert step["change"] == {"kind": "open", "ts": NOW, "price": 100.0}
    assert "XYZ" in out["symbols"] and "XYZ" in out["caps"]


def test_a_stock_over_the_step_buys_one_share():
    w = World()
    w.quotes["BIGX"] = {"last": 712.0, "bid": 711.9, "ask": 712.1, "fresh": True}
    out = watching(w, row("BIGX", price=712.0, entry_ts=NOW))
    (step,) = kinds(out, "step")
    assert step["qty"] == 1 and step["limit"] == pytest.approx(712.12)


def test_the_same_answer_twice_sends_nothing_twice():
    w = World()
    r = row(entry_ts=NOW)
    watching(w, r)
    again = w.at(4).run(answer({HOST: [r]}, feed_now=w.now))
    assert kinds(again, "step") == [] and kinds(again, "skip") == []


# -- positions already open ---------------------------------------------------------------------------
def test_already_open_when_watching_began_is_taken_by_default():
    w = World()
    out = w.run(answer({HOST: [row(entry_ts=NOW - 600)]}))
    (step,) = kinds(out, "step")
    assert step["step"] == "already_open" and step["change"]["kind"] == "already_open"


def test_already_open_is_skipped_when_the_setting_says_skip():
    w = World(take_open=False)
    out = w.run(answer({HOST: [row(entry_ts=NOW - 600)]}))
    assert kinds(out, "step") == []
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_ALREADY_OPEN and skip["why"] == "already open when watching began, not taken"


def test_an_entry_first_seen_a_minute_late_is_already_open():
    w = World()
    w.run(answer())
    out = w.at(2).run(answer({HOST: [row(entry_ts=NOW - 90)]}, feed_now=w.now))
    assert kinds(out, "step")[0]["step"] == "already_open"


def test_the_feeds_unknown_entry_is_already_open():
    w = World()
    w.run(answer())
    out = w.at(2).run(answer({HOST: [row(entry_ts=NOW, known=False)]}, feed_now=w.now))
    assert kinds(out, "step")[0]["step"] == "already_open"


def test_already_open_far_from_the_market_is_a_misread():
    w = World()
    out = w.run(answer({HOST: [row(price=103.0, entry_ts=NOW - 600)]}))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_MISREAD and "3.0% from the market" in skip["why"]


# -- adds -------------------------------------------------------------------------------------------
def _add(ts, price, prev):
    return {"ts": ts, "price": price, "prev_price": prev}


def test_an_add_is_one_more_step_once_it_settles():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    moved = dict(base, price=99.5, adds=[_add(NOW + 30, 99.5, 100.0)])
    w.quotes["XYZ"] = {"last": 99.4, "bid": 99.38, "ask": 99.42, "fresh": True}
    early = w.at(32).run(answer({HOST: [moved]}, feed_now=NOW + 32))
    assert kinds(early, "step") == []                                  # still moving: wait for it to settle
    out = w.at(36).run(answer({HOST: [moved]}, feed_now=NOW + 36))
    (step,) = kinds(out, "step")
    assert step["step"] == "add" and step["change"]["kind"] == "add" and step["their_price"] == 99.5
    assert w.book[step["pos_id"]]["adds_followed"] == 1


def test_an_average_that_flickers_for_a_few_seconds_is_one_add():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    adds = [_add(NOW + 30, 99.8, 100.0), _add(NOW + 32, 99.6, 99.8), _add(NOW + 34, 99.5, 99.6)]
    moved = dict(base, price=99.5, adds=adds)
    w.quotes["XYZ"] = {"last": 99.4, "bid": 99.38, "ask": 99.42, "fresh": True}
    out = w.at(40).run(answer({HOST: [moved]}, feed_now=NOW + 40))
    assert len(kinds(out, "step")) == 1


def test_an_average_that_comes_back_is_no_add():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    moved = dict(base, adds=[_add(NOW + 30, 104.0, 100.0), _add(NOW + 31, 100.0, 104.0)])
    out = w.at(40).run(answer({HOST: [moved]}, feed_now=NOW + 40))
    assert kinds(out, "step") == [] and kinds(out, "skip") == []


def test_an_entry_filling_in_pieces_is_not_an_add():
    w = World()
    base = row(entry_ts=NOW, adds=[_add(NOW + 2, 100.1, 100.0), _add(NOW + 3, 100.15, 100.1)])
    out = watching(w, base, after=10)
    assert [a["step"] for a in kinds(out, "step")] == ["entry"]
    again = w.at(12).run(answer({HOST: [base]}, feed_now=NOW + 12))
    assert kinds(again, "step") == []


def test_adds_past_the_limit_are_skipped_and_said():
    w = World(adds=2)
    base = row(entry_ts=NOW)
    watching(w, base)
    adds = []
    for n, at in enumerate((30, 60, 90), start=1):
        adds.append(_add(NOW + at, 100.0 - n * 0.1, 100.0 - (n - 1) * 0.1))
        out = w.at(at + 5).run(answer({HOST: [dict(base, price=100.0 - n * 0.1, adds=list(adds))]},
                                      feed_now=NOW + at + 5))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_ADDS_DONE and "follows 2 adds" in skip["why"]
    pos = next(iter(w.book.values()))
    assert pos["adds_followed"] == 2 and pos["steps"] == 3


def test_adds_made_before_the_bot_held_it_are_not_followed():
    w = World()
    old = row(entry_ts=NOW - 600, price=99.0, adds=[_add(NOW - 300, 99.0, 100.0)])
    w.quotes["XYZ"] = {"last": 99.0, "bid": 98.98, "ask": 99.02, "fresh": True}
    out = w.run(answer({HOST: [old]}))
    assert [a["step"] for a in kinds(out, "step")] == ["already_open"]
    again = w.at(5).run(answer({HOST: [old]}, feed_now=NOW + 5))
    assert kinds(again, "step") == []


def test_an_add_far_from_the_market_is_a_misread():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    moved = dict(base, price=97.0, adds=[_add(NOW + 30, 97.0, 100.0)])
    out = w.at(40).run(answer({HOST: [moved]}, feed_now=NOW + 40))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_MISREAD and skip["step"] == "add"


# -- the position leaves the bar ------------------------------------------------------------------
def test_the_host_closing_sells_all_of_it():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    out = w.at(60).run(answer({HOST: [dict(base, status="closed", exit_ts=NOW + 58)]}, feed_now=NOW + 60))
    (close,) = kinds(out, "close")
    assert close["qty"] == 4 and close["change"] == {"kind": "close", "ts": NOW + 58, "price": None}
    assert close["why"] == f"{HOST} closed XYZ"


def test_a_row_reopened_for_the_same_stock_is_the_same_position():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    again = row(entry_ts=NOW + 50)
    out = w.at(60).run(answer({HOST: [dict(base, status="unknown"), again]}, feed_now=NOW + 60))
    assert kinds(out, "close") == [] and kinds(out, "step") == []
    (rekey,) = kinds(out, "rekey")
    assert rekey["row_id"] == again["id"]


def test_a_short_is_covered_when_the_host_covers():
    w = World()
    short = row(side="short", entry_ts=NOW)
    watching(w, short)
    out = w.at(60).run(answer({HOST: [dict(short, status="closed", exit_ts=NOW + 59)]}, feed_now=NOW + 60))
    (close,) = kinds(out, "close")
    assert close["side"] == "short"


def test_with_exit_on_you_the_bot_says_so_and_keeps_the_shares():
    w = World(exit="you")
    base = row(entry_ts=NOW)
    watching(w, base)
    closed = answer({HOST: [dict(base, status="closed", exit_ts=NOW + 58)]}, feed_now=NOW + 60)
    out = w.at(60).run(closed)
    assert kinds(out, "close") == []
    (tell,) = kinds(out, "tell")
    assert "the exit is yours" in tell["why"]
    assert kinds(w.at(62).run(closed), "tell") == []                    # said once


# -- off air, hidden, the clock --------------------------------------------------------------------
def test_off_air_sells_every_position_of_that_host():
    w = World()
    w.quotes["ABCD"] = {"last": 50.0, "bid": 49.99, "ask": 50.01, "fresh": True}
    watching(w, row(entry_ts=NOW), row("ABCD", price=50.0, entry_ts=NOW))
    assert len(w.book) == 2
    gone = answer({HOST: [dict(row(entry_ts=NOW), status="closed", left_bar=True),
                          dict(row("ABCD", price=50.0, entry_ts=NOW), status="closed", left_bar=True)]},
                  left={HOST: NOW + 100}, feed_now=NOW + 170)
    out = w.at(170).run(gone)
    assert {a["symbol"] for a in kinds(out, "close")} == {"XYZ", "ABCD"}
    assert all(a["change"]["kind"] == "off_air" for a in kinds(out, "close"))


def test_back_on_air_their_bar_is_already_open_once_the_switch_wait_ends():
    w = World()
    r = row(entry_ts=NOW)
    watching(w, r)
    w.at(170).run(answer({HOST: [dict(r, status="closed", left_bar=True)]}, left={HOST: NOW + 100},
                         feed_now=NOW + 170))
    assert w.book == {}
    out = w.at(400).run(answer({HOST: [r]}, feed_now=NOW + 400))
    assert kinds(out, "step") == [] and {v["code"] for v in out["waits"].values()} == {LT_RETURN_SWITCH}
    (said,) = kinds(out, "note")
    assert "previous host's rows" in said["why"]
    out = w.at(400 + LT_RETURN_HOLD_SEC).run(answer({HOST: [r]}, feed_now=NOW + 400 + LT_RETURN_HOLD_SEC))
    (step,) = kinds(out, "step")
    assert step["step"] == "already_open"


def test_the_bar_hidden_ten_minutes_sells_but_nine_does_not():
    w = World()
    r = row(entry_ts=NOW)
    watching(w, r)
    w.at(10).run(answer({HOST: [r]}, visible=False, feed_now=NOW + 10))
    nine = w.at(10 + 540).run(answer({HOST: [r]}, visible=False, feed_now=NOW + 550))
    assert kinds(nine, "close") == []
    ten = w.at(10 + 600).run(answer({HOST: [r]}, visible=False, feed_now=NOW + 610))
    (close,) = kinds(ten, "close")
    assert close["change"]["kind"] == "hidden" and "hidden for 10 min" in close["why"]
    back = w.at(700).run(answer({HOST: [r]}, feed_now=NOW + 700))
    assert kinds(back, "step")[0]["step"] == "already_open"           # visible again: already open


def test_a_feed_silent_ten_minutes_sells():
    w = World()
    watching(w, row(entry_ts=NOW))
    w.at(10).run(answer(state="unreachable"))
    assert kinds(w.at(300).run(answer(state="unreachable")), "close") == []
    out = w.at(611).run(answer(state="unreachable"))
    assert kinds(out, "close")[0]["change"]["kind"] == "hidden"


def test_the_sell_all_time_sells_everything_and_opens_nothing():
    w = World()
    watching(w, row(entry_ts=NOW))
    w.sell_all_ts = NOW + 100
    out = w.at(100).run(answer({HOST: [row(entry_ts=NOW), row("ABCD", price=50.0, entry_ts=NOW + 99)]},
                               feed_now=NOW + 100))
    (close,) = kinds(out, "close")
    assert close["change"]["kind"] == "sell_all" and "never holds overnight" in close["why"]
    assert kinds(out, "step") == [] and kinds(out, "skip")[0]["code"] == LT_AFTER_SELL_ALL


# -- doubtful reads ------------------------------------------------------------------------------
def test_a_feed_reading_behind_the_stream_opens_nothing_but_still_closes():
    w = World()
    held = row(entry_ts=NOW)
    watching(w, held)
    out = w.at(30).run(answer({HOST: [dict(held, status="closed", exit_ts=NOW + 20), row("ABCD", entry_ts=NOW + 25)]},
                              behind=45.0, feed_now=NOW + 30))
    assert kinds(out, "step") == []
    skip = kinds(out, "skip")[0]
    assert skip["code"] == LT_FEED_BEHIND and "45 s behind the stream" in skip["why"]
    (close,) = kinds(out, "close")                                     # a late close is still a true one
    assert close["symbol"] == "XYZ"


def test_a_feed_that_does_not_answer_holds_the_closes_until_it_does():
    w = World()
    held = row(entry_ts=NOW)
    watching(w, held)
    assert kinds(w.at(30).run(answer(state="unreachable")), "close") == []
    back = w.at(60).run(answer({HOST: [dict(held, status="closed", exit_ts=NOW + 20)]}, feed_now=NOW + 60))
    assert len(kinds(back, "close")) == 1


def test_a_ticker_being_checked_waits_then_steps_when_it_settles():
    w = World()
    checking = row(entry_ts=NOW, ticker={"state": "checking", "why": "reading IBKR's tape"})
    out = watching(w, checking)
    assert kinds(out, "step") == [] and out["waits"]
    settled = dict(checking, ticker={"state": "as_read", "why": None})
    out = w.at(6).run(answer({HOST: [settled]}, feed_now=NOW + 6))
    assert kinds(out, "step")[0]["step"] == "entry"


def test_a_ticker_check_that_never_settles_is_a_skip():
    w = World()
    checking = row(entry_ts=NOW, ticker={"state": "checking", "why": None})
    watching(w, checking)
    out = w.at(40).run(answer({HOST: [checking]}, feed_now=NOW + 40))
    assert kinds(out, "skip")[0]["code"] == LT_TICKER_UNSETTLED


def test_an_unchecked_ticker_is_a_skip_with_why():
    w = World()
    out = watching(w, row(entry_ts=NOW, ticker={"state": "unchecked", "why": "neither fits"}))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_TICKER_UNSETTLED and "neither fits" in skip["why"]


def test_no_fresh_quote_waits_then_skips():
    w = World()
    w.quotes["XYZ"] = None
    out = watching(w, row(entry_ts=NOW))
    assert out["waits"] and kinds(out, "skip") == []
    out = w.at(40).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 40))
    assert kinds(out, "skip")[0]["code"] == LT_NO_QUOTE


# -- large caps only, the allowance, sides --------------------------------------------------------
def test_a_small_cap_is_skipped_and_says_its_size():
    w = World()
    w.caps["XYZ"] = 2.1e9
    (skip,) = kinds(watching(w, row(entry_ts=NOW)), "skip")
    assert skip["code"] == LT_SMALL_CAP and "$2.1B" in skip["why"] and "large caps only" in skip["why"]


def test_an_unknown_market_cap_is_a_skip_and_a_pending_one_a_wait():
    w = World()
    w.caps["XYZ"] = "pending"
    out = watching(w, row(entry_ts=NOW))
    assert out["waits"] and not kinds(out, "skip")
    w.caps["XYZ"] = None
    out = w.at(6).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 6))
    assert kinds(out, "skip")[0]["code"] == LT_CAP_UNKNOWN


def test_a_step_over_the_allowance_is_skipped_with_the_dollars_used():
    w = World()
    old = row("OLD", entry_ts=NOW - 50)
    w.book["TRADER1|long|OLD"] = {"id": "TRADER1|long|OLD", "host": HOST, "row_id": old["id"], "symbol": "OLD",
                                  "side": "long", "qty": 23, "cost_usd": 2300.0, "steps": 1, "adds_followed": 0,
                                  "opened_ts": NOW - 50, "state": "open", "order": None}
    w.quotes["OLD"] = dict(QUOTE)
    w.run(answer({HOST: [old]}))
    out = w.at(2).run(answer({HOST: [old, row(entry_ts=NOW + 1)]}, feed_now=NOW + 2))
    (skip,) = [a for a in kinds(out, "skip") if a["symbol"] == "XYZ"]
    assert skip["code"] == LT_ALLOWANCE and "allowance used: $2,300 of $2,500" in skip["why"]


def test_shorts_follow_the_sides_setting_and_the_short_hours():
    w = World(sides="long")
    (skip,) = kinds(watching(w, row(side="short", entry_ts=NOW)), "skip")
    assert skip["code"] == LT_SHORTS_OFF
    w = World()
    w.short_closed = "New shorts open at 09:35 ET, never premarket: it is 09:12 ET."
    (skip,) = kinds(watching(w, row(side="short", entry_ts=NOW)), "skip")
    assert skip["code"] == LT_SHORT_HOURS and "09:35" in skip["why"]


def test_a_short_sells_at_the_bid_with_a_buy_stop_five_percent_over():
    w = World()
    (step,) = kinds(watching(w, row(side="short", entry_ts=NOW)), "step")
    assert step["limit"] == pytest.approx(99.96) and step["stop"] == pytest.approx(104.96)


def test_the_bot_never_trades_against_a_position():
    w = World()
    w.held[("XYZ", "short")] = 100.0
    (skip,) = kinds(watching(w, row(entry_ts=NOW)), "skip")
    assert skip["code"] == LT_AGAINST and "you hold XYZ short on Paper" in skip["why"]
    w = World()
    other = row(host=OTHER, side="short", entry_ts=NOW)
    w.run(answer({HOST: [], OTHER: []}))
    w.at(2).run(answer({HOST: [], OTHER: [other]}, feed_now=NOW + 2))
    out = w.at(4).run(answer({HOST: [row(entry_ts=NOW + 3)], OTHER: [other]}, feed_now=NOW + 4))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_AGAINST and f"for {OTHER}" in skip["why"]


# -- who trades: approve, watch only ----------------------------------------------------------------
def test_entry_on_you_asks_and_an_approval_sends():
    w = World(entry="you", exit="nova")
    out = watching(w, row(entry_ts=NOW))
    (ask,) = [a["ask"] for a in kinds(out, "ask")]
    assert kinds(out, "step") == [] and ask["qty"] == 4 and ask["text"].startswith(f"{HOST} bought XYZ at 100.00")
    w.answers = {ask["id"]: True}
    out = w.at(5).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 5))
    (step,) = kinds(out, "step")
    assert step["approved"] is True and kinds(out, "drop_ask")


def test_a_skipped_ask_and_an_expired_ask_are_skips():
    w = World(entry="you")
    out = watching(w, row(entry_ts=NOW))
    ask = kinds(out, "ask")[0]["ask"]
    w.answers = {ask["id"]: False}
    assert kinds(w.at(5).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 5)), "skip")[0]["code"] == LT_ASK_SKIPPED
    w = World(entry="you")
    watching(w, row(entry_ts=NOW))
    out = w.at(2 + 61).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 63))
    assert kinds(out, "skip")[0]["code"] == LT_ASK_EXPIRED


def test_an_ask_is_withdrawn_when_the_host_closes_first():
    w = World(entry="you")
    r = row(entry_ts=NOW)
    watching(w, r)
    out = w.at(5).run(answer({HOST: [dict(r, status="closed", exit_ts=NOW + 4)]}, feed_now=NOW + 5))
    (drop,) = kinds(out, "drop_ask")
    assert "closed XYZ before you answered" in drop["why"]


def test_entry_and_exit_on_you_only_watches():
    w = World(entry="you", exit="you")
    out = watching(w, row(entry_ts=NOW))
    assert kinds(out, "step") == [] and kinds(out, "ask") == []
    (note,) = kinds(out, "note")
    assert "would buy 4 at 100.04" in note["why"]


# -- the operator's switches and the desk ----------------------------------------------------------
def test_turning_a_key_off_or_the_bot_off_sells():
    w = World()
    watching(w, row(entry_ts=NOW))
    w.requests = {"sell_hosts": {HOST: "key_off"}}
    out = w.at(5).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 5))
    assert kinds(out, "close")[0]["change"]["kind"] == "key_off"
    w = World()
    watching(w, row(entry_ts=NOW))
    w.requests = {"sell_all": "bot_off"}
    out = w.at(5).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 5))
    assert kinds(out, "close")[0]["change"]["kind"] == "bot_off"


def test_a_bot_that_cannot_open_skips_once_and_takes_it_already_open_later():
    w = World()
    w.can = {"ok": False, "code": LT_BOT_OFF, "why": "the Bot switch is off"}
    out = watching(w, row(entry_ts=NOW))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_BOT_OFF
    assert kinds(w.at(4).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 4)), "skip") == []
    w.can = {"ok": True, "code": None, "why": None}
    out = w.at(6).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 6))
    assert kinds(out, "step")[0]["step"] == "already_open"


def test_a_key_off_host_is_not_traded_and_turning_it_on_takes_what_is_open():
    w = World(key=False)
    assert kinds(watching(w, row(entry_ts=NOW)), "step") == []
    w.st[HOST]["key"] = True
    out = w.at(5).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 5))
    assert kinds(out, "step")[0]["step"] == "already_open"


def test_a_position_sold_outside_is_not_bought_back():
    w = World()
    r = row(entry_ts=NOW)
    watching(w, r)
    w.book.clear()
    w.no_reentry = {r["id"]}
    assert kinds(w.at(5).run(answer({HOST: [r]}, feed_now=NOW + 5)), "step") == []


# -- the pure pieces --------------------------------------------------------------------------------
def test_behind_the_stream_reads_like_the_page():
    # the bar's clock 10:00:00 read at 10:00:45 ET (2026-10-15 is EDT, UTC-4)
    read = 1_792_072_845.0
    assert feed_rows.behind_sec("10:00:00", read) == 45.0
    assert feed_rows.behind_sec("10:00:50", read) == 0.0               # a clock a little ahead reads 0
    assert feed_rows.behind_sec(None, read) is None


def test_add_groups_fold_and_settle():
    adds = [_add(NOW + 10, 99.0, 100.0), _add(NOW + 12, 98.0, 99.0), _add(NOW + 30, 97.0, 98.0)]
    settled, pending = feed_rows.add_groups(adds, NOW, NOW + 31)
    assert len(settled) == 1 and settled[0]["to_price"] == 98.0 and pending is True
    settled, pending = feed_rows.add_groups(adds, NOW, NOW + 40)
    assert len(settled) == 2 and pending is False


def test_rules_shares_and_prices():
    assert rules.shares(500.0, 100.04) == 4
    assert rules.shares(500.0, 712.12) == 1
    assert rules.limits("long", {"bid": 0.501, "ask": 0.5033, "last": 0.502}, 5.0) == (0.5233, None)
    assert rules.limits("short", {"bid": 20.0, "ask": 20.02, "last": 20.01}, 5.0) == (19.98, 20.98)


def test_already_open_waits_for_the_bar_to_show_it_then_skips():
    from bot.live_trader.constants_live_trader import LT_NOT_ON_BAR

    w = World()
    stale = dict(row(entry_ts=NOW - 600), on_bar=False)            # the feed still holds it open; the bar does not
    out = w.run(answer({HOST: [stale]}))
    assert kinds(out, "step") == [] and out["waits"]
    out = w.at(31).run(answer({HOST: [stale]}, feed_now=NOW + 31))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_NOT_ON_BAR and "not on TRADER1's bar now" in skip["why"]
    w = World()
    assert kinds(w.run(answer({HOST: [dict(row(entry_ts=NOW - 600), on_bar=True)]})), "step")


def test_an_etf_always_passes_the_large_cap_rule():
    w = World()
    w.caps["XYZ"] = "etf"                                          # Yahoo's quoteType ETF: no market cap needed
    (step,) = kinds(watching(w, row(entry_ts=NOW)), "step")
    assert step["step"] == "entry"


def test_the_market_read_calls_an_etf_an_etf(monkeypatch):
    import fundamentals

    from bot.live_trader import market

    rows = {"TQQQ": {"market_cap": None, "quote_type": "ETF"}, "BIGX": {"market_cap": 3e11, "quote_type": "EQUITY"},
            "NONE": {"market_cap": None, "quote_type": "EQUITY"}}
    monkeypatch.setattr(fundamentals, "peek_cached", lambda s: rows.get(s))
    monkeypatch.setattr(fundamentals, "fetch_failed", lambda s: False)
    assert (market.cap("TQQQ"), market.cap("BIGX"), market.cap("NONE"), market.cap("NEWX")) == ("etf", 3e11, None,
                                                                                                "pending")


# -- bad reads (operator, 2026-10-14: an abnormal read never buys or averages more) -------------------------
def _with(ans, name, **host):
    ans["hosts"][name].update(host)
    return ans


def test_the_previous_hosts_rows_under_the_next_hosts_tag_are_never_bought():
    """At a hand-over the bar can show the previous host's rows under the next host's name tag for minutes."""
    w = World()
    w.st[OTHER] = settings(key=False)
    theirs = row("XYZ", host=OTHER, price=100.0, entry_ts=NOW - 900)
    w.run(answer({OTHER: [theirs], HOST: []}))
    gone = dict(theirs, status="closed", exit_ts=NOW + 1)
    shown = row("XYZ", price=100.0, entry_ts=NOW + 2)
    out = w.at(3).run(answer({OTHER: [gone], HOST: [shown]}, left={OTHER: NOW + 1}, feed_now=NOW + 3))
    assert kinds(out, "step") == []
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_OTHER_HOST and f"{OTHER}'s" in skip["why"] and "not copied" in skip["why"]


def test_rows_shown_under_two_hosts_tags_are_bought_by_neither():
    """The rows can switch to the next host's a few seconds before the name tags do: whose they are is unknown."""
    w = World()
    w.run(answer({HOST: [], OTHER: []}))
    early = row("XYZ", price=100.0, entry_ts=NOW + 2)
    theirs = row("XYZ", host=OTHER, price=100.0, entry_ts=NOW + 8)
    out = w.at(10).run(answer({HOST: [early], OTHER: [theirs]}, feed_now=NOW + 10))
    assert kinds(out, "step") == []
    assert sorted(s["host"] for s in kinds(out, "skip") if s["code"] == LT_OTHER_HOST) == [HOST, OTHER]


def test_a_row_the_feeds_previous_day_showed_is_never_bought():
    w = World()
    w.run(answer())
    ans = answer({HOST: [row("XYZ", price=100.0, entry_ts=NOW)]}, feed_now=NOW + 2)
    ans["previous"] = [["long", "XYZ", 100.0]]
    out = w.at(2).run(ans)
    assert kinds(out, "step") == []
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_OTHER_HOST and "previous day" in skip["why"]


def test_another_hosts_row_long_before_is_not_theirs():
    w = World()
    w.st[OTHER] = settings(key=False)
    long_ago = row("XYZ", host=OTHER, price=100.0, entry_ts=NOW - 7200, status="closed", exit_ts=NOW - 3600)
    w.run(answer({OTHER: [long_ago], HOST: []}))
    out = w.at(2).run(answer({OTHER: [long_ago], HOST: [row("XYZ", price=100.0, entry_ts=NOW + 1)]},
                             feed_now=NOW + 2))
    (step,) = kinds(out, "step")
    assert step["step"] == "entry"


def test_a_side_the_reader_cannot_read_whole_waits_then_steps_once_it_reads():
    """A row that scrolls (three or more positions) or a cut pair: nothing opens on that side until it reads."""
    w = World()
    w.run(answer())
    fresh = row(entry_ts=NOW)
    out = w.at(2).run(_with(answer({HOST: [fresh]}, feed_now=NOW + 2), HOST, unread=["long"]))
    assert kinds(out, "step") == []
    (wait,) = out["waits"].values()
    assert wait["code"] == LT_ROW_UNREAD and "not reading whole" in wait["text"]
    clean = w.at(6).run(answer({HOST: [fresh]}, feed_now=NOW + 6))
    (step,) = kinds(clean, "step")
    assert step["symbol"] == "XYZ"


def test_a_side_unread_too_long_is_a_skip_and_the_other_side_is_untouched():
    w = World()
    w.run(answer())
    fresh = row(entry_ts=NOW)
    w.at(2).run(_with(answer({HOST: [fresh]}, feed_now=NOW + 2), HOST, unread=["long"]))
    out = w.at(40).run(_with(answer({HOST: [fresh]}, feed_now=NOW + 40), HOST, unread=["long"]))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_ROW_UNREAD and "did not read whole" in skip["why"]
    other = World()
    other.run(answer())
    shorts_unread = other.at(2).run(_with(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 2), HOST,
                                          unread=["short"]))
    assert len(kinds(shorts_unread, "step")) == 1


def test_an_unread_side_never_adds():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    moved = dict(base, price=99.5, adds=[_add(NOW + 30, 99.5, 100.0)])
    w.quotes["XYZ"] = {"last": 99.4, "bid": 99.38, "ask": 99.42, "fresh": True}
    out = w.at(40).run(_with(answer({HOST: [moved]}, feed_now=NOW + 40), HOST, unread=["long"]))
    assert kinds(out, "step") == [] and next(iter(out["waits"].values()))["code"] == LT_ROW_UNREAD


def test_an_add_no_add_could_make_is_a_misread():
    """An add moves their average toward the market: 100.00 -> 99.20 with the market at 100.50 is a misread."""
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    w.quotes["XYZ"] = {"last": 100.5, "bid": 100.48, "ask": 100.52, "fresh": True}
    moved = dict(base, price=99.2, adds=[_add(NOW + 30, 99.2, 100.0)])
    out = w.at(40).run(answer({HOST: [moved]}, feed_now=NOW + 40))
    assert kinds(out, "step") == []
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_ADD_IMPLAUSIBLE and "not between" in skip["why"]


def test_an_add_between_the_old_average_and_the_market_is_followed():
    w = World()
    base = row(entry_ts=NOW)
    watching(w, base)
    w.quotes["XYZ"] = {"last": 100.5, "bid": 100.48, "ask": 100.52, "fresh": True}
    moved = dict(base, price=100.3, adds=[_add(NOW + 30, 100.3, 100.0)])
    out = w.at(40).run(answer({HOST: [moved]}, feed_now=NOW + 40))
    (step,) = kinds(out, "step")
    assert step["step"] == "add"


def test_a_read_without_the_streams_clock_opens_nothing_but_still_closes():
    w = World()
    w.run(answer())
    no_clock = answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 2)
    no_clock["feed_now"] = None
    out = w.at(2).run(no_clock)
    assert kinds(out, "step") == []
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_NO_CLOCK and "clock" in skip["why"]
    back = w.at(4).run(answer({HOST: [row(entry_ts=NOW)]}, feed_now=NOW + 4))
    (step,) = kinds(back, "step")
    assert step["step"] == "already_open"          # blocked when first seen: taken as already open once it reads
    held = World()
    base = row(entry_ts=NOW)
    watching(held, base)
    closed = answer({HOST: [dict(base, status="closed", exit_ts=NOW + 20)]}, feed_now=NOW + 22)
    closed["feed_now"] = None
    (close,) = kinds(held.at(22).run(closed), "close")
    assert close["symbol"] == "XYZ"


def test_a_ticker_glued_to_its_price_is_far_from_the_market_and_skipped():
    """XYZI 14.03 read as XYZ 114.03: the 1.5% rule stops it before any step."""
    w = World()
    w.quotes["XYZ"] = {"last": 14.03, "bid": 14.02, "ask": 14.04, "fresh": True}
    out = watching(w, row("XYZ", price=114.03, entry_ts=NOW))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_MISREAD and kinds(out, "step") == []


def test_a_ticker_a_scroll_cut_short_is_skipped_as_a_misread():
    """ABCD 85.12 read as D 85.12 at a scrolling row's edge: D's own market is nowhere near it."""
    w = World()
    w.quotes["D"] = {"last": 60.0, "bid": 59.99, "ask": 60.01, "fresh": True}
    out = watching(w, row("D", price=85.12, entry_ts=NOW))
    (skip,) = kinds(out, "skip")
    assert skip["code"] == LT_MISREAD and kinds(out, "step") == []


def test_a_clock_that_is_no_time_of_day_reads_as_no_clock():
    assert feed_rows.time_of_day("09:34:97") is None and feed_rows.time_of_day("24:00:00") is None
    assert feed_rows.time_of_day("09:34:57") == (9, 34, 57)
    assert feed_rows.clock_ts("2026-10-15", "09:34:97") is None
    assert feed_rows.behind_sec("09:34:97", NOW) is None


def test_unread_sides_count_only_text_holding_a_price_in_the_last_twenty_seconds():
    date = "2026-10-15"

    def line(clock, **unparsed):
        return {"clock": clock, "traders": {n: {"positions": [], "unparsed": u} for n, u in unparsed.items()}}

    log = [
        line("09:59:00", **{HOST: ["long:7.32|ABCD350.94|EFGH5.58|IJK"]}),   # superseded before the window
        line("10:00:00", **{HOST: []}),                                        # in force when the window began
        line("10:00:30", **{HOST: ["long:nopositionsLONGnopositions"], OTHER: ["XYZ12.301"]}),
        line("10:00:40", **{HOST: ["short:NAME SHORTXYZ259.47"]}),
        line("10:00:50", **{HOST: ["long:ABCD350.941"]}),                     # after the moment asked about
    ]
    got = feed_rows.unread_sides(log, date, feed_rows.clock_ts(date, "10:00:45"))
    assert got == {HOST: {"short"}, OTHER: {"long", "short"}}
    assert feed_rows.unread_sides(None, date, None) == {}


def test_other_host_matches_any_average_to_the_cent():
    mine = row("XYZ", price=100.004, entry_ts=NOW)
    theirs = row("XYZ", host=OTHER, price=101.0, entry_ts=NOW - 60, adds=[_add(NOW - 30, 100.0, 101.0)])
    hosts = {HOST: {"rows": [mine]}, OTHER: {"rows": [theirs]}}
    assert feed_rows.other_host(HOST, mine, hosts, set()) == (OTHER, 100.0)
    assert feed_rows.other_host(HOST, dict(mine, side="short"), hosts, set()) is None
    assert feed_rows.other_host(HOST, mine, {HOST: {"rows": [mine]}}, {("long", "XYZ", 100.0)}) == (None, 100.0)


# -- the bar's own moves (decide_bar): a blank bar, a hand-over that lingers --------------------------
def two_held(w):
    w.quotes["ABCD"] = {"last": 50.0, "bid": 49.99, "ask": 50.01, "fresh": True}
    a, b = row(entry_ts=NOW), row("ABCD", price=50.0, entry_ts=NOW + 5)
    watching(w, a, b, after=6)
    assert set(w.book) == {f"{HOST}|long|XYZ", f"{HOST}|long|ABCD"}
    return a, b


def blanked(rows, ts):
    """Every row closed within the same second: the bar went blank."""
    return [dict(r, status="closed", exit_ts=ts + i * 0.5) for i, r in enumerate(rows)]


def test_a_whole_bar_blank_holds_the_sells_and_positions_back_at_their_averages_are_the_same():
    w = World()
    a, b = two_held(w)
    gone = blanked([a, b], NOW + 100)
    out = w.at(101).run(answer({HOST: gone}, feed_now=NOW + 101, bars={HOST: []}))
    assert kinds(out, "close") == [] and len(w.book) == 2
    assert {v["code"] for v in out["waits"].values()} == {LT_BLANK_BAR}
    assert {n["symbol"] for n in kinds(out, "note")} == {"XYZ", "ABCD"}
    assert all("went blank" in n["why"] for n in kinds(out, "note"))
    assert kinds(w.at(150).run(answer({HOST: gone}, feed_now=NOW + 150, bars={HOST: []})), "close") == []

    a2, b2 = row(entry_ts=NOW + 160), row("ABCD", price=50.0, entry_ts=NOW + 160.5)
    back = answer({HOST: gone + [a2, b2]}, feed_now=NOW + 161, bars={HOST: ["long:ABCD", "long:XYZ"]})
    first = w.at(161).run(back)
    assert kinds(first, "close") == [] and kinds(first, "step") == []     # the rest get a moment to come back
    out = w.at(166).run(dict(back, feed_now=NOW + 166))
    assert kinds(out, "close") == [] and kinds(out, "step") == []
    assert {r["row_id"] for r in kinds(out, "rekey")} == {a2["id"], b2["id"]}
    assert all("very average" in r["why"] for r in kinds(out, "rekey"))
    later = w.at(170).run(dict(back, feed_now=NOW + 170))
    assert kinds(later, "close") == [] and kinds(later, "step") == []    # not bought again either

    added = dict(a2, price=99.7, adds=[{"ts": NOW + 200, "price": 99.7, "prev_price": 100.0}])
    out = w.at(210).run(answer({HOST: gone + [added, b2]}, feed_now=NOW + 210, bars={HOST: ["long:XYZ"]}))
    (step,) = kinds(out, "step")
    assert step["step"] == "add" and step["symbol"] == "XYZ"            # the same position follows its adds


def test_after_a_blank_a_position_not_back_at_its_average_is_sold_when_the_bar_returns():
    w = World()
    a, b = two_held(w)
    gone = blanked([a, b], NOW + 100)
    w.at(101).run(answer({HOST: gone}, feed_now=NOW + 101, bars={HOST: []}))
    a2, b2 = row(entry_ts=NOW + 160), row("ABCD", price=50.40, entry_ts=NOW + 160)
    out = w.at(170).run(answer({HOST: gone + [a2, b2]}, feed_now=NOW + 170,
                               bars={HOST: ["long:ABCD", "long:XYZ"]}))
    (close,) = kinds(out, "close")
    assert close["symbol"] == "ABCD" and "without ABCD long at 50.00" in close["why"]
    (rekey,) = kinds(out, "rekey")
    assert rekey["symbol"] == "XYZ" and rekey["row_id"] == a2["id"]


def test_a_bar_that_stays_blank_past_the_limit_is_sold():
    w = World()
    a, b = two_held(w)
    gone = blanked([a, b], NOW + 100)
    w.at(101).run(answer({HOST: gone}, feed_now=NOW + 101, bars={HOST: []}))
    early = NOW + 100 + LT_BLANK_HOLD_SEC - 2
    assert kinds(w.at(early - NOW).run(answer({HOST: gone}, feed_now=early, bars={HOST: []})), "close") == []
    late = NOW + 101 + LT_BLANK_HOLD_SEC
    out = w.at(late - NOW).run(answer({HOST: gone}, feed_now=late, bars={HOST: []}))
    assert {c["symbol"] for c in kinds(out, "close")} == {"XYZ", "ABCD"}
    assert all("stayed empty" in c["why"] for c in kinds(out, "close")) and w.book == {}


def test_the_clock_and_the_operator_never_wait_on_a_blank_bar():
    w = World()
    a, b = two_held(w)
    gone = blanked([a, b], NOW + 100)
    w.at(101).run(answer({HOST: gone}, feed_now=NOW + 101, bars={HOST: []}))
    w.sell_all_ts = NOW + 110
    out = w.at(111).run(answer({HOST: gone}, feed_now=NOW + 111, bars={HOST: []}))
    assert {c["symbol"] for c in kinds(out, "close")} == {"XYZ", "ABCD"}
    assert all(c["change"]["kind"] == "sell_all" for c in kinds(out, "close"))

    w2 = World()
    a, b = two_held(w2)
    gone = blanked([a, b], NOW + 100)
    w2.at(101).run(answer({HOST: gone}, feed_now=NOW + 101, bars={HOST: []}))
    w2.requests = {"sell_hosts": {HOST: True}}
    out = w2.at(103).run(answer({HOST: gone}, feed_now=NOW + 103, bars={HOST: []}))
    assert {c["change"]["kind"] for c in kinds(out, "close")} == {"key_off"} and len(kinds(out, "close")) == 2


@pytest.mark.parametrize("case", ["apart", "one_left", "bar_not_empty", "no_bar"])
def test_closes_that_are_not_a_whole_bar_blank_sell_at_once(case):
    w = World()
    a, b = two_held(w)
    rows = blanked([a, b], NOW + 100)
    bars = {HOST: []}
    if case == "apart":
        rows[1]["exit_ts"] = NOW + 103                                   # three seconds apart: the host's own sells
    elif case == "one_left":
        rows.append(row("EFGH", price=20.0, entry_ts=NOW + 6))           # a position stayed on the bar
        bars = {HOST: ["long:EFGH"]}
    elif case == "bar_not_empty":
        bars = {HOST: ["long:ABCD"]}
    else:
        bars = None                                                     # the feed sends no bar: no blank to see
    out = w.at(104).run(answer({HOST: rows}, feed_now=NOW + 104, bars=bars))
    assert {c["symbol"] for c in kinds(out, "close")} == {"XYZ", "ABCD"}


def test_after_a_return_the_rows_on_the_bar_wait_for_every_slot_to_switch():
    w = World()
    w.quotes["ABCD"] = {"last": 50.0, "bid": 49.99, "ask": 50.01, "fresh": True}
    w.quotes["EFGH"] = {"last": 20.0, "bid": 19.99, "ask": 20.01, "fresh": True}
    w.run(answer())
    w.at(10).run(answer({HOST: []}, left={HOST: NOW + 5}, feed_now=NOW + 10))      # off air (the lunch break)
    stale = [row(entry_ts=NOW + 100), row("ABCD", price=50.0, entry_ts=NOW + 100)]  # another show's rows, this tag
    out = w.at(101).run(answer({HOST: stale}, feed_now=NOW + 101))
    assert kinds(out, "step") == [] and {v["code"] for v in out["waits"].values()} == {LT_RETURN_SWITCH}
    assert kinds(w.at(250).run(answer({HOST: stale}, feed_now=NOW + 250)), "step") == []

    # Every slot switches in one second: the old rows close and the host's own open as they do.
    switched = blanked(stale, NOW + 300) + [row("EFGH", price=20.0, entry_ts=NOW + 300.2)]
    out = w.at(301).run(answer({HOST: switched}, feed_now=NOW + 301, bars={HOST: ["long:EFGH"]}))
    assert kinds(out, "step") == []                                     # a moment for every slot to switch
    out = w.at(306).run(answer({HOST: switched}, feed_now=NOW + 306, bars={HOST: ["long:EFGH"]}))
    (step,) = kinds(out, "step")
    assert step["symbol"] == "EFGH" and step["step"] == "already_open"   # their position, already open
    assert not any(a["kind"] == "step" and a["symbol"] in ("XYZ", "ABCD") for a in out["actions"])


def test_rows_that_fill_an_empty_bar_together_are_already_open():
    w = World(take_open=False)
    w.quotes["ABCD"] = {"last": 50.0, "bid": 49.99, "ask": 50.01, "fresh": True}
    out = watching(w, row(entry_ts=NOW), row("ABCD", price=50.0, entry_ts=NOW + 0.5))
    assert kinds(out, "step") == [] and {a["code"] for a in kinds(out, "skip")} == {LT_ALREADY_OPEN}
    alone = watching(World(take_open=False), row(entry_ts=NOW))
    assert kinds(alone, "step")[0]["step"] == "entry"                  # one row on its own is a new trade
