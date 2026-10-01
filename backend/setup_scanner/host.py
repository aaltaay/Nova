"""The host every lane calls, on the live engine (ADR 022, ADR 029, ADR 031).

A lane (``setup_scanner/lane.py``) asks its host for pillars, the tape, a place to
save a row and journal a line, the clock, and whether it may propose; the live
engine answers from Nova's feeds, a replay (``eyes/replay.py``) from a recording.
Moved out of ``engine.py`` so the engine keeps one concern -- the loop that feeds
the lanes. ``SetupEngine`` mixes this in; it owns the attributes read here.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from constants_bot import BOT_LEVEL_EYES
from setup_scanner import grade as _grade
from setup_scanner import tape_flow, tape_gap

logger = logging.getLogger("setup_scanner.engine")


class LaneHost:
    def pillars(self, sym: str, now: float) -> dict:
        """One pillars read per symbol and moment, shared by every lane that asks (a new leg is read
        by each template's lane on the same bar)."""
        memo = self.__dict__.setdefault("_pillars_memo", {"now": None, "read": {}})
        if memo["now"] != now:
            memo["now"], memo["read"] = now, {}
        if sym not in memo["read"]:
            memo["read"][sym] = _grade.read_pillars(sym, now)
        return memo["read"][sym]

    def tape_books(self, sym: str) -> list:
        return self.tape.books(sym) if self.tape is not None else []

    def tape_prints(self, sym: str) -> list:
        return self.tape.prints(sym) if self.tape is not None else []

    def tape_since(self, sym: str) -> float | None:
        since = getattr(self.tape, "since", None) if self.tape is not None else None
        return since(sym) if since is not None else None

    def flow(self, sym: str, now: float, p: tape_flow.FlowParams) -> dict:
        """One tape flow reading per symbol, moment and numbers, shared by every lane that asks (ADR 034).

        A window that touches an IBKR feed gap reads ``blind``, and the baseline starts after the gap (#673)."""
        memo = self.__dict__.setdefault("_flow_memo", {})
        if memo.get("now") != now:
            memo.clear()
            memo["now"] = now
        key = (sym, p)
        if key not in memo:
            gaps = self.feed_gaps(now)
            reading = tape_flow.evaluate(now=now, books=self.tape_books(sym), prints=self.tape_prints(sym), p=p,
                                         history_from=tape_gap.history_from(gaps, self.tape_since(sym), now))
            memo[key] = tape_gap.hold_flow(reading, gaps, now, p.window_sec)
        return memo[key]

    def feed_gaps(self, now: float) -> list[dict]:
        """The live IBKR feed's gaps a tape read at ``now`` can reach (#673), read once per moment."""
        memo = self.__dict__.setdefault("_gaps_memo", {"now": None, "gaps": []})
        if memo["now"] != now:
            from ibkr import feed_pulse
            memo["now"], memo["gaps"] = now, feed_pulse.gaps_for_tape(now)
        return memo["gaps"]

    def flow_reading(self, setup_id: str) -> dict | None:
        """The newest flow reading on a triggered setup and its template's flush rule (ADR 034; Nova's bot)."""
        for lane in getattr(self, "lanes", []):
            got = lane.flow_last.get(setup_id)
            if got is not None:
                f = lane.p.flush
                return {**got, "template_id": lane.p.template_id,
                        "policy": {"mode": f.mode, "hold_sec": f.hold_sec, "trail_r": f.trail_r, "min_r": f.min_r}}
        return None

    def tape_line(self, sym: str) -> dict:
        if self.tape is None:
            return {"depth": False, "tape": False}
        return {"depth": self.tape.has_depth(sym), "tape": self.tape.has_tape(sym)}

    def save(self, row: dict) -> None:
        if self.store is None:
            return
        try:
            self.store.upsert(row)
        except Exception:
            logger.exception("setup scanner: could not save %s", row.get("id"))

    def journal(self, event: dict) -> None:
        try:
            self._journal_fn({"ts": self._clock(), "date": self.session, "source": self.source,
                              "bot": self._bot_state_fn(), **event})
        except Exception:
            logger.warning("setup scanner: journal write failed", exc_info=True)

    def audit(self, **kw: Any) -> None:
        self._audit_fn(**kw)

    def clock(self) -> float:
        return self._clock()

    def levels(self) -> dict:
        """``{"chosen": None, "levels": {SETUP: effective level}, ...}`` (ADR 031, 042: ``bot.setup_levels``);
        an unreadable answer is every setup Off."""
        try:
            out = self._levels_fn()
        except Exception:
            logger.warning("setup scanner: levels unread -- every setup proposes nothing", exc_info=True)
            return {"chosen": None, "levels": {}}
        return out if isinstance(out, dict) else {"chosen": None, "levels": {}}

    def can_propose(self, setup_type: str | None = None) -> bool:
        """Not on a replay desk; and for a setup, only at effective Eyes or above (ADR 031: Off is
        silent). A setup at Strategy proposes too (ADR 042): the proposal says whether the bot or
        Auto-entry takes it (``taker``)."""
        if self._replay_fn():
            return False
        if setup_type is None:
            return True
        return int((self.levels().get("levels") or {}).get(setup_type) or 0) >= BOT_LEVEL_EYES

    def taker(self, sym: str, setup_type: str) -> str | None:
        """``"bot"`` / ``"auto_entry"`` when Nova would take this setup's go trigger on ``sym`` by itself
        (the bot is Active, the setup at Strategy, the stock set to Bot or Auto-entry), else None."""
        from bot.first_pullback.admit import taker

        return taker(sym, setup_type)

    # -- triggers to whoever trades them (ADR 030) --------------------------------
    def add_trigger_listener(self, fn: Callable[[dict], None]) -> None:
        if fn not in self._trigger_listeners:
            self._trigger_listeners.append(fn)

    def remove_trigger_listener(self, fn: Callable[[dict], None]) -> None:
        if fn in self._trigger_listeners:
            self._trigger_listeners.remove(fn)

    def on_trigger(self, event: dict) -> None:
        """The playing lane's setup triggered: tell the listeners, on the live feed only."""
        if not self.can_propose():
            return
        for fn in list(self._trigger_listeners):
            try:
                fn({**event, "source": self.source})
            except Exception:
                logger.exception("setup scanner: a trigger listener failed on %s", event.get("setup_id"))
