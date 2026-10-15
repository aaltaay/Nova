"""The Live Trader bot's decision: one feed answer against the last, as orders to send, skips and asks. Pure.

``decide(prev, answer, book, ctx)`` takes the last pass's snapshot (memory: the hosts' open rows and what was
decided for each, a few KB), this pass's answer (``answer.read``), what the bot holds (``book``) and the pass's
context (``ctx``: the clock, the settings, whether the bot may open, the operator's requests and the market as
callables -- fakes in tests), and answers ``{snapshot, actions, waits, symbols, caps}``. It reads no clock and
does no I/O of its own: the watcher sends what it says.

Closes come first (``decide_closes``): a close only ever reduces what the bot holds, so no doubt about the feed
holds one back -- only the bar's own moves (``decide_bar``: a whole bar blank for a refresh) delay one. Steps -- an entry, a position already open, an add -- follow (``decide_steps``), each through
``rules.check``. Rules: architecture/schema/bot.md ("The Live Trader bot"), ADR 055.
"""
from __future__ import annotations

import copy
from typing import Any

from bot.live_trader import decide_bar, decide_closes, decide_steps
from bot.live_trader.constants_live_trader import (
    LT_FEED_BEHIND,
    LT_FEED_BEHIND_SEC,
    LT_FEED_DOWN,
    LT_HIDDEN_SEC,
)


def empty_snapshot() -> dict[str, Any]:
    return {"hosts": {}, "blind_since": None, "hidden_since": None, "blind_done": False, "hidden_done": False,
            "asks": {}, "told": [], "seq": 0, "blanks": {}}


def doubt(answer: dict[str, Any]) -> tuple[str, str] | None:
    """``(code, words)`` when this answer may not open a step: the feed down, its capture stopped or not live,
    or its read more than ``LT_FEED_BEHIND_SEC`` behind the stream; None when it is fresh."""
    if answer["state"] != "ok":
        return LT_FEED_DOWN, f"the TraderTV feed is not answering ({answer.get('error') or answer['state']})"
    age, behind = answer.get("read_age_sec"), answer.get("behind_sec")
    if age is None:
        return LT_FEED_DOWN, "the TraderTV feed has not read the stream today"
    if not answer.get("live"):
        return LT_FEED_DOWN, "the stream is not live"
    if age > LT_FEED_BEHIND_SEC:
        return LT_FEED_BEHIND, f"the feed has read nothing for {age:.0f} s"
    if behind is not None and behind > LT_FEED_BEHIND_SEC:
        return LT_FEED_BEHIND, f"the feed reads {behind:.0f} s behind the stream"
    return None


def _silent_sec(answer: dict[str, Any], snap: dict[str, Any], now: float) -> float:
    """How long the bar has gone unread: the read's age and lag when the feed answers, else since it stopped."""
    if answer["state"] == "ok" and answer.get("read_age_sec") is not None:
        return max(answer["read_age_sec"] or 0.0, answer.get("behind_sec") or 0.0)
    since = snap["blind_since"] if snap["blind_since"] is not None else now
    return now - since


def decide(prev: dict[str, Any] | None, answer: dict[str, Any], book: dict[str, dict[str, Any]],
           ctx: dict[str, Any]) -> dict[str, Any]:
    snap = copy.deepcopy(prev) if prev else empty_snapshot()
    now = ctx["now"]
    out = {"snapshot": snap, "actions": [], "waits": {}, "symbols": set(), "caps": set()}

    doubtful = doubt(answer)
    if doubtful is None:
        snap["blind_since"], snap["blind_done"] = None, False
    elif snap["blind_since"] is None:
        snap["blind_since"] = now
    silent = _silent_sec(answer, snap, now) if doubtful else 0.0
    blind = doubtful is not None and silent >= LT_HIDDEN_SEC

    hidden = False
    if answer["state"] == "ok" and doubtful is None:
        if answer.get("bar_visible"):
            snap["hidden_since"], snap["hidden_done"] = None, False
        else:
            if snap["hidden_since"] is None:
                snap["hidden_since"] = now
            hidden = now - snap["hidden_since"] >= LT_HIDDEN_SEC
    flags = {"doubt": doubtful, "blind": blind, "hidden": hidden, "silent": silent,
             "bar_hidden": snap["hidden_since"] is not None,
             "visible": answer["state"] == "ok" and bool(answer.get("bar_visible")),
             "clock": answer.get("feed_now") is not None}

    for pos in book.values():
        out["symbols"].add(pos["symbol"])          # the bot holds a line on every stock it holds
    flags["bar"] = decide_bar.blanks(snap, answer, now)
    decide_closes.closes(snap, answer, book, ctx, flags, out)
    if blind:
        snap["blind_done"] = True
    if hidden:
        snap["hidden_done"] = True
    decide_steps.steps(snap, answer, book, ctx, flags, out)
    return out
