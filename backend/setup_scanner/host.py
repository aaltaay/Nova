"""The host every lane calls, on the live engine (ADR 022, ADR 029, ADR 031).

A lane (``setup_scanner/lane.py``) asks its host for pillars, the tape, a place to
save a row and journal a line, the clock, and whether it may propose; the live
engine answers from Nova's feeds, a replay (``eyes/replay.py``) from a recording.
Moved out of ``engine.py`` so the engine keeps one concern -- the loop that feeds
the lanes. ``SetupEngine`` mixes this in; it owns the attributes read here.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from constants_bot import BOT_LEVEL_EYES, BOT_SETUP_FIRST_PULLBACK
from constants_setups import SETUPS_THIN_SIZE_TTL_SEC
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

    def _sleeve(self) -> dict | None:
        """The desk venue's bot sleeve (ADR 042), re-read at most every ``SETUPS_THIN_SIZE_TTL_SEC``; None
        when unread."""
        memo = self.__dict__.setdefault("_sleeve_memo", {"at": None, "caps": None})
        mono = time.monotonic()
        if memo["at"] is None or mono - memo["at"] >= SETUPS_THIN_SIZE_TTL_SEC:
            memo["at"] = mono
            try:
                from bot.persist import load_session
                from bot.sleeve import of

                memo["caps"] = dict(of(load_session()))
            except Exception:
                logger.warning("setup scanner: the desk's risk per trade could not be read", exc_info=True)
                memo["caps"] = None
        return memo["caps"]

    def risk_usd(self) -> float | None:
        """The desk's risk per trade -- the desk venue's bot sleeve, the size every Nova buy and the operator's
        Stage use (ADR 042); None when unread. The liquidity sizes its walk through the book by it (2026-10-01)."""
        caps = self._sleeve()
        try:
            return float(caps["risk_usd"]) if caps else None
        except (KeyError, TypeError, ValueError):
            return None

    def order_shares(self, risk: float | None) -> int | None:
        """The sleeve's size for a setup risking ``risk`` a share: the risk per trade over it, cut to the
        sleeve's max shares (a short's borrow pillar reads it, ADR 049); None when either is unknown."""
        caps = self._sleeve()
        try:
            usd, cap = float(caps["risk_usd"]), int(caps["max_shares"])
        except (KeyError, TypeError, ValueError):
            return None
        if risk is None or float(risk) <= 0:
            return None
        return min(int(usd // float(risk)), cap) or None

    # -- what a short's detector and grade read (ADR 049): memory only, never a wait --------------
    def short_context(self, sym: str, now: float) -> dict:
        """``{prior_close, ssr_yesterday}`` for a short's detector: the board's prior close (else the line's
        tick 9) and whether SSR carries from yesterday (IBKR's daily reads in memory). A stock trading under
        its prior close with no daily reads yet has them asked for on a worker thread."""
        memo = self.__dict__.setdefault("_short_ctx_memo", {"now": None, "read": {}})
        if memo["now"] != now:
            memo["now"], memo["read"] = now, {}
        if sym not in memo["read"]:
            from short_sale import ssr

            prior = _grade.prior_close(sym)
            yesterday = ssr.yesterday_on(sym, now)
            if yesterday is None and prior is not None:
                mb = getattr(self, "bars", {}).get(sym)
                last = mb.completed[-1].c if mb is not None and getattr(mb, "completed", None) else None
                if last is not None and last < prior:
                    ssr.request_history(sym, now)       # a worker thread; yesterday reads unknown until it lands
            memo["read"][sym] = {"prior_close": prior, "ssr_yesterday": yesterday}
        return memo["read"][sym]

    def dilution(self, sym: str, now: float) -> tuple[bool | None, str | None]:
        """``(on file, words)`` from the stock read's "Dilution on file" reading (``stock_read.dilution_reader``,
        from memory; a missing read is queued and reads unknown)."""
        from stock_read import dilution_reader

        row = dilution_reader.view(sym, now) or {}
        state = row.get("state")
        if state == "warn":
            return True, f"dilution on file: {row.get('value')}"
        if state == "ok":
            return False, None
        return None, None

    def borrow(self, sym: str) -> dict | None:
        """IBKR's cached shortable estimate (tick 236): ``{shares, state, age_sec}``; None when never read."""
        from ibkr import shortability

        snap = shortability.cached(sym)
        if not snap:
            return None
        return {"shares": snap.get("shortable_shares"), "state": snap.get("state"), "age_sec": snap.get("age_sec")}

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
            return
        memo = self.__dict__.get("_triggered_memo")
        if row.get("triggered_at") and memo is not None and memo["session"] == row.get("session_date"):
            key = (row["symbol"], row.get("template_id"), row.get("setup_type") or BOT_SETUP_FIRST_PULLBACK)
            memo["ids"].setdefault(key, set()).add(row["id"])

    def stored_triggers(self, sym: str, template_id: str, setup_type: str) -> list[str]:
        """Today's ids on ``sym`` (one template, one setup) whose stored row holds a trigger: a lane made
        after a restart never writes a setup over a stored trade (one row per trigger, 2026-10-02). The
        day is read from ``setups.db`` once and kept as rows are saved."""
        if self.store is None or not self.session:
            return []
        memo = self.__dict__.get("_triggered_memo")
        if memo is None or memo["session"] != self.session:
            memo = {"session": self.session, "ids": self.store.triggered_on(self.session)}
            self.__dict__["_triggered_memo"] = memo
        return sorted(memo["ids"].get((sym.upper(), template_id, setup_type), ()))

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
