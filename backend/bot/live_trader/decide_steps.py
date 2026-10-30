"""The Live Trader bot's steps: an entry, a position already open, an add -- or a skip or an ask (ADR 055). Pure.

``decide`` calls it after the closes. Per host with its key on, in the feed's order, each open row the bot does
not hold is one entry decision, remembered in the snapshot so it is made once: ``taken``, ``skipped``, ``noted``
(Entry and Exit on You: the bot only watches), ``asked`` (Entry on You, Exit on Bot: the operator approves,
``decide_asks``),
``waiting`` (a quote, a market cap or a ticker check), ``blocked`` (the bot could not open when the row was
first seen) or ``released`` (the bot sold it off air or while the bar was hidden). A blocked or released row,
and every open row when the key turns on or the host comes back on air, is already open: ``take_open`` decides.
A held position follows its host's adds, one settled add at a time (``feed_rows.add_groups``), up to ``adds``.
A read in doubt opens and adds nothing (bot.md, "Bad reads"): a row another host showed (``LT_OTHER_HOST``), a side
the reader could not read whole (``LT_ROW_UNREAD``), an add no add could make (``LT_ADD_IMPLAUSIBLE``), no stream
clock (``LT_NO_CLOCK``). The bar's own moves (``decide_bar``) hold a take while a whole bar is blank
(``LT_BLANK_BAR``) or just after a return (``LT_RETURN_SWITCH``), and rows that fill an empty bar together are
already open (``feed_rows.filled_together``). Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

from typing import Any

from bot.live_trader import decide_asks, decide_bar, decide_held, feed_rows, rules
from bot.live_trader.constants_live_trader import (
    LT_ADD_IS_SALE,
    LT_ADDS_DONE,
    LT_AFTER_SELL_ALL,
    LT_BLANK_BAR,
    LT_ALREADY_OPEN,
    LT_HIDDEN,
    LT_NO_CLOCK,
    LT_NOT_ON_BAR,
    LT_OFF_AIR,
    LT_OPEN_FRESH_SEC,
    LT_OTHER_HOST,
    LT_RETURN_SWITCH,
    LT_ROW_UNREAD,
    LT_TICKER_UNSETTLED,
    LT_WAIT_SEC,
)
from bot.live_trader.decide_closes import hms
from constants_stock_mode import STOCK_MODE_APPROVE, STOCK_MODE_SIGNAL
from followed_traders.pricing import priceable
from stock_mode.model import mode_of

UNSETTLED_WAIT = "the ticker check is still running: taken once it settles, if it still meets the entry rules"


def _blocked(ctx: dict[str, Any], flags: dict[str, Any], on_air: bool, name: str) -> tuple[str, str] | None:
    can = ctx["can_open"]
    if not can["ok"]:
        return can["code"], can["why"]
    sell_ts = ctx.get("sell_all_ts")
    if sell_ts is not None and ctx["now"] >= sell_ts:
        return LT_AFTER_SELL_ALL, f"it is past {hms(sell_ts)[:5]} ET: no new positions until the next session"
    if flags["doubt"] is not None:
        return flags["doubt"]
    if flags["bar_hidden"]:
        return LT_HIDDEN, "the bar is hidden: no read of it now"
    if not flags.get("clock", True):
        return LT_NO_CLOCK, "the stream's clock could not be read, so how far behind the feed reads is unknown"
    if not on_air:
        return LT_OFF_AIR, f"{name} is off air"
    return None


class _Pass:
    """One pass's steps for one host: the context, the snapshot and the running allowance."""

    def __init__(self, snap, answer, book, ctx, out, used, closing=frozenset()):
        self.snap, self.answer, self.book, self.ctx, self.out, self.used = snap, answer, book, ctx, out, used
        self.closing = closing                 # positions whose close this pass sends (``decide_closes``)
        self.now = ctx["now"]
        self.feed_now = answer.get("feed_now")
        self.previous = {(p[0], p[1], float(p[2])) for p in answer.get("previous") or ()}

    # -- shared --------------------------------------------------------------------------------------
    def check(self, name, st, side, symbol, their_price, ticker, since, *, entry: bool,
              prev_price: float | None = None, change_ts: float | None = None,
              already_open: bool = False) -> dict[str, Any]:
        self.out["symbols"].add(symbol)
        self.out["caps"].add(symbol)
        found = rules.against(self.book, self.ctx, side, symbol, self.closing) if entry else None
        return rules.check(side=side, symbol=symbol, their_price=their_price, settings=st,
                           quote=self.ctx["quote"](symbol), cap=self.ctx["cap"](symbol), ticker=ticker,
                           used_usd=self.used.get(name, 0.0), against=found[0] if found else None,
                           against_wait=bool(found and found[1]),
                           short_closed=self.ctx["short_closed"](self.now) if side == "short" else None,
                           priceable=priceable(symbol), now=self.now, wait_since=since, prev_price=prev_price,
                           ssr=self.ctx["ssr"](symbol) if side == "short" else "off",
                           market=decide_held.market_since(self, symbol, change_ts), already_open=already_open)

    def read_doubt(self, name, r, since, unread, *, entry: bool) -> dict[str, Any] | None:
        """A skip or a wait when the read of ``r`` is in doubt (bot.md, "Bad reads"); None when it reads clean."""
        if entry:
            found = feed_rows.other_host(name, r, self.answer.get("hosts") or {}, self.previous)
            if found is not None:
                whose, price = found
                at = f"{r['symbol']} {r['side']} at {rules.price_text(price)}"
                return rules.verdict(rules.SKIP, LT_OTHER_HOST, (
                    f"{at} is also {whose}'s (the same stock, side and average to the cent): the bar showed one "
                    f"host's rows under another's name tag -- not copied") if whose else (
                    f"{at} was on the feed's previous day too (the same stock, side and average to the cent): "
                    "the bar may be showing an earlier show's rows -- not copied"))
        if r["side"] in unread:
            return rules.waited(LT_ROW_UNREAD,
                                f"{name}'s {r['side']} row is not reading whole (it scrolls, or a pair is cut)",
                                f"{name}'s {r['side']} row did not read whole in {LT_WAIT_SEC:.0f} s", since,
                                self.now)
        return None

    def skip(self, name, r, pid, step, code, why, change) -> None:
        self.out["actions"].append({"kind": "skip", "host": name, "pos_id": pid, "row_id": r["id"],
                                    "symbol": r["symbol"], "side": r["side"], "step": step, "code": code,
                                    "why": why, "change": change})

    def wait(self, pid, r, v) -> None:
        self.out["waits"][pid] = {"symbol": r["symbol"], "code": v["code"], "text": v["text"]}

    def hold(self, name, r, pid, code, why) -> None:
        """A take waiting on the bar's own move, said once (``act.note``) and on the card's waits."""
        self.wait(pid, r, {"code": code, "text": why})
        self.out["actions"].append({"kind": "note", "host": name, "pos_id": pid, "row_id": r["id"],
                                    "symbol": r["symbol"], "side": r["side"], "step": code.lower(),
                                    "change": {"kind": "already_open", "ts": r["entry_ts"], "price": r["price"]},
                                    "why": f"not taking {r['symbol']} yet -- {why}"})

    def send(self, name, r, pid, step, plan, change, *, approved: bool) -> None:
        self.used[name] = self.used.get(name, 0.0) + plan["cost_usd"]
        self.out["actions"].append({"kind": "step", "host": name, "pos_id": pid, "row_id": r["id"],
                                    "symbol": r["symbol"], "side": r["side"], "step": step,
                                    "qty": plan["qty"], "limit": plan["limit"], "stop": plan["stop"],
                                    "cost_usd": plan["cost_usd"], "their_price": change["price"],
                                    "ssr": plan.get("ssr"), "change": change, "approved": approved})

    def note(self, name, r, pid, step, plan, change) -> None:
        stop = f" with a buy stop {rules.price_text(plan['stop'])}" if plan.get("stop") else ""
        self.out["actions"].append({"kind": "note", "host": name, "pos_id": pid, "row_id": r["id"],
                                    "symbol": r["symbol"], "side": r["side"], "step": step, "change": change,
                                    "why": f"would {rules.verb(r['side'])} {plan['qty']} at "
                                           f"{rules.price_text(plan['limit'])}{stop} -- Entry and Exit are You: "
                                           "the bot only watches"})

    # -- an entry ------------------------------------------------------------------------------------
    def entry(self, name, st, r, rs, pid, blocked, unread) -> None:
        change = {"kind": "open" if rs["kind"] == "open" else "already_open", "ts": r["entry_ts"],
                  "price": r["price"]}
        step = "entry" if rs["kind"] == "open" else "already_open"
        if rs["fate"] in ("taken", "skipped", "noted"):
            return
        if rs["fate"] == "asked":
            rs["fate"] = decide_asks.follow(self, name, st, r, pid, rs.get("ask_id"), blocked, unread, entry=True)
            if rs["fate"] == "taken":
                self.taken(r, rs)
            return
        if rs["fate"] == "unsettled":
            # The ticker check outlasted the wait: said once, then judged again once it settles -- as a position the
            # host already holds, so the price the market moved to since is judged too (2026-10-19, SHAWN's SPCX
            # short at 14:01: the check settled "as read" after the wait and the skip was final, never taken).
            if (r.get("ticker") or {}).get("state") == "checking":
                self.wait(pid, r, {"code": LT_TICKER_UNSETTLED, "text": UNSETTLED_WAIT})
                return
            rs.update(fate=None, kind="already_open", since=None, late_ticker=True)
            step, change = "already_open", {**change, "kind": "already_open"}
        # Kept on the row until its verdict is final: a wait or a block after the check settles is still the row the
        # bot saw open, never a trade open before watching began (``take_open``; PR #1094 review).
        late = bool(rs.get("late_ticker"))
        if blocked:
            if rs["fate"] not in ("blocked", "released"):
                self.skip(name, r, pid, step, blocked[0], blocked[1], change)
                rs["fate"] = "blocked"
            return
        if rs["fate"] in ("blocked", "released"):
            rs.update(fate=None, kind="already_open", since=None)
            step, change = "already_open", {**change, "kind": "already_open"}
        if step == "already_open" and not st["take_open"] and not late:
            rs["fate"] = "skipped"
            self.skip(name, r, pid, step, LT_ALREADY_OPEN, "already open when watching began, not taken", change)
            return
        v = self.read_doubt(name, r, rs.get("since"), unread, entry=True)
        if v is None and step == "already_open" and r.get("on_bar") is False:
            # A trade the feed still holds open from before the host left can be gone from their bar: taken only
            # once the bar shows it (the feed closes it otherwise).
            v = rules.waited(LT_NOT_ON_BAR, f"waiting for {name}'s bar to show {r['symbol']}",
                             f"{r['symbol']} is not on {name}'s bar now", rs.get("since"), self.now)
        elif v is None:
            v = self.check(name, st, r["side"], r["symbol"], r["price"], r.get("ticker"), rs.get("since"),
                           entry=True, already_open=step == "already_open")
        if v["verdict"] == rules.WAIT:
            rs["fate"], rs["since"] = "waiting", rs.get("since") or self.now
            self.wait(pid, r, v)
            return
        if v["verdict"] == rules.SKIP:
            slow = v["code"] == LT_TICKER_UNSETTLED and (r.get("ticker") or {}).get("state") == "checking"
            rs["fate"] = "unsettled" if slow else "skipped"
            self.skip(name, r, pid, step, v["code"], v["text"], change)
            return
        mode = mode_of(st["entry"], st["exit"])
        approved = rs.pop("approved_ts", None) == change["ts"]   # a yes kept through a borrow wait: used once
        if mode == STOCK_MODE_SIGNAL:
            rs["fate"] = "noted"
            self.note(name, r, pid, step, v["plan"], change)
        elif mode == STOCK_MODE_APPROVE and not approved:
            rs["fate"], rs["ask_id"] = "asked", decide_asks.ask(self, name, r, pid, step, v["plan"], change)
        else:
            rs["fate"] = "taken"
            self.send(name, r, pid, step, v["plan"], change, approved=approved)
            self.taken(r, rs)

    def taken(self, r, rs) -> None:
        groups, _pending = feed_rows.add_groups(r["adds"], r["entry_ts"], self.feed_now)
        rs["groups_done"] = len(groups)        # adds made before the bot held it are not followed

    # -- an add --------------------------------------------------------------------------------------
    def add(self, name, st, r, rs, pos, blocked, unread) -> None:
        groups, _pending = feed_rows.add_groups(r["adds"], r["entry_ts"], self.feed_now)
        if rs.get("groups_done") is None:
            rs["groups_done"] = len(groups)    # first sight of a held position (a restart): no old add is new
        if pos["state"] != "open":
            return                             # its order is in flight: the next pass
        pid = pos["id"]
        if rs.get("trim_change") and not blocked:
            decide_held.trim(self, name, st, r, pos, rs.pop("trim_change"))   # held while a key was off
        if rs.get("add_ask_id"):
            fate = decide_asks.follow(self, name, st, r, pid, rs["add_ask_id"], blocked, unread, entry=False)
            if fate != "asked":
                rs["add_ask_id"] = None
                rs["groups_done"] += 1
            return
        if rs["groups_done"] >= len(groups):
            return
        i = rs["groups_done"]
        g = groups[i]
        prev = g["from_price"] or (groups[i - 1]["to_price"] if i > 0 else r.get("entry_price"))
        change = {"kind": "add", "ts": g["last_ts"], "price": g["to_price"]}
        limit = st["adds"]
        spent = limit is not None and pos["adds_followed"] >= limit
        if blocked or spent:
            # A sale is judged as any add is (bad reads, the band, the market since): it trims even with every add
            # spent, and with a key or the Bot switch off it waits on this row for them (Codex review, PR #1024).
            sold = decide_held.sale_of(self, name, st, r, rs, prev, g, unread)
            if sold and not blocked:
                rs["groups_done"] += 1
                self.skip(name, r, pid, "add", LT_ADD_IS_SALE, sold, change)
                decide_held.trim(self, name, st, r, pos, change)
                return
            if sold:
                decide_held.hold_trim(self, name, r, rs, pos, change, blocked[1])
        if blocked or spent:
            code, why = blocked or (LT_ADDS_DONE, f"{name} added to {r['symbol']}: this bot follows "
                                                  f"{limit} add{'' if limit == 1 else 's'}")
            rs["groups_done"] += 1
            self.skip(name, r, pid, "add", code, why, change)
            return
        v = self.read_doubt(name, r, rs.get("add_since"), unread, entry=False)
        if v is None:
            v = self.check(name, st, r["side"], r["symbol"], g["to_price"], None, rs.get("add_since"), entry=False,
                           prev_price=prev, change_ts=g["first_ts"])
        if v["verdict"] == rules.WAIT:
            rs["add_since"] = rs.get("add_since") or self.now
            self.wait(pid, r, v)
            return
        rs["add_since"] = None
        if v["verdict"] == rules.SKIP:
            rs["groups_done"] += 1
            self.skip(name, r, pid, "add", v["code"], v["text"], change)
            if v["code"] == LT_ADD_IS_SALE:
                decide_held.trim(self, name, st, r, pos, change)
            return
        mode = mode_of(st["entry"], st["exit"])
        approved = rs.pop("add_approved_ts", None) == change["ts"]   # a yes kept through a borrow wait: used once
        if mode == STOCK_MODE_APPROVE and not approved:
            rs["add_ask_id"] = decide_asks.ask(self, name, r, pid, "add", v["plan"], change, prev_price=prev)
            return
        rs["groups_done"] += 1
        if mode == STOCK_MODE_SIGNAL:
            self.note(name, r, pid, "add", v["plan"], change)
        else:
            self.send(name, r, pid, "add", v["plan"], change, approved=approved)


def _host_state() -> dict[str, Any]:
    return {"rows": {}, "keyed": False, "on_air": None}


def steps(snap: dict[str, Any], answer: dict[str, Any], book: dict[str, dict[str, Any]], ctx: dict[str, Any],
          flags: dict[str, Any], out: dict[str, Any]) -> None:
    closing = {a["pos_id"] for a in out["actions"] if a["kind"] in ("close", "rekey")}
    run = _Pass(snap, answer, book, ctx, out, rules.used_by_host(book),
                {a["pos_id"] for a in out["actions"] if a["kind"] == "close" and not a.get("trim")})
    if answer["state"] != "ok":
        decide_asks.expire(run)                # an ask times out with no read of the feed too
        return
    # A row a held position follows under its glued ticker is no new entry while its check runs (#1010); settled on
    # another stock, the position sells (``decide_closes``) and the row is judged as any other.
    followed = {p["row_id"] for p in book.values()} | {a["row_id"] for a in out["actions"] if a["kind"] == "rekey"}
    no_reentry = ctx.get("no_reentry") or set()
    for name in answer.get("order") or []:
        h = answer["hosts"][name]
        st = ctx["settings"](name)
        hs = snap["hosts"].setdefault(name, _host_state())
        on_air = h.get("left_ts") is None
        came_back = hs.get("on_air") is False and on_air
        first = bool(st["key"]) and not hs.get("keyed")
        hs.update(on_air=on_air, keyed=bool(st["key"]))
        returned = decide_bar.returning(hs, h, run.now, came_back)
        ids = {r["id"] for r in h["rows"]}
        hs["rows"] = {k: v for k, v in hs["rows"].items() if k in ids}     # today's rows only: memory stays small
        open_rows = sorted((r for r in h["rows"] if r["status"] == "open" and not r.get("left_bar")),
                           key=lambda r: r["entry_ts"])
        open_ids = {r["id"] for r in open_rows}
        for ask_id, ask in list(snap["asks"].items()):
            if ask["host"] == name and (not st["key"] or ask["row_id"] not in open_ids):
                decide_asks.drop(run, ask_id, "the key is off" if not st["key"] else
                                 f"{name} closed {ask['symbol']} before you answered")
        if not st["key"]:
            decide_held.key_off_adds(run, name, st, open_rows, hs, book, closing)
            continue
        blocked = _blocked(ctx, flags, on_air, name)
        unread = set(h.get("unread") or ())
        blank = (flags.get("bar") or {}).get("hosts", {}).get(name)
        for r in open_rows:
            pid = feed_rows.position_id(name, r["side"], r["symbol"])
            held = (LT_BLANK_BAR, blank) if blank else (LT_RETURN_SWITCH, returned.get(r["id"]))
            if held[1] and pid not in book:   # the bar's own moves (decide_bar): no take until it settles
                run.hold(name, r, pid, *held)
                continue
            rs = hs["rows"].get(r["id"])
            if rs is None:
                late = not r["known"] or feed_rows.filled_together(r, h["rows"]) or (
                    run.feed_now is not None and run.feed_now - r["entry_ts"] > LT_OPEN_FRESH_SEC)
                rs = hs["rows"][r["id"]] = {"fate": None, "since": None, "groups_done": None, "ask_id": None,
                                            "kind": "already_open" if (first or came_back or late) else "open"}
            elif (first or came_back) and rs["fate"] in (None, "blocked", "released", "waiting"):
                rs.update(fate=None, kind="already_open", since=None)
            pos = book.get(pid)
            if pos is not None:
                if pos["row_id"] == r["id"] and pid not in closing:
                    run.add(name, st, r, rs, pos, blocked, unread)
                continue
            if pid in closing or r["id"] in no_reentry or (
                    r["id"] in followed and (r.get("ticker") or {}).get("state") == "checking"):
                continue
            run.entry(name, st, r, rs, pid, blocked, unread)

