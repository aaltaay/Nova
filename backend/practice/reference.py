"""Where a practice fill's price comes from (ADR 020): the replay, or the live feed.

``MarketReference`` is the one door the practice broker reads the market
through. ``ReplayReference`` is the Sim venue and delegates to ``sim.practice``
unchanged (the loaded historical download or capture at the playhead).
``LiveReference`` is the Paper venue: the fresh L1 last from ``ibkr.ticks``
(within ``PRACTICE_LIVE_FRESH_SEC``), failing that the newest tape print in
the local archive (``l2.tape``) inside the same window, the live top of book
from ``ibkr.depth.state``, and a refusal (``PRACTICE_NO_LIVE_PRINT``) when
neither a fresh last nor a recent print exists. Only a print that sets a price
counts, as a last or for a resting order (``sale_conditions.row_sets_price``,
#511): an odd lot or an average-price print can sit dollars from the market.
A practice fill is never a guess: an absent price is stated, not filled in.
Each reference also names its session's close (``session_close_ts``) so a DAY order knows when it
expires (``practice.order_rules``): the replayed window's end on Sim, the
desk's ``PRACTICE_SESSION_CLOSE_HOUR_ET`` on Paper. ``SimReference`` is what
the Sim broker actually holds (ADR 020 live-edge amendment): the live
reference while the Sim clock is at the live edge, the replay reference off
it -- one door, decided per call by ``sim.session_clock.live_edge``.
"""
from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from constants_practice import (
    PRACTICE_LIVE_FRESH_SEC,
    PRACTICE_NO_LIVE_PRINT_CODE,
    PRACTICE_NO_LIVE_PRINT_REASON,
)
from sale_conditions import row_sets_price
from sim.fill_model import Reference

Print = tuple[float, float]


@runtime_checkable
class MarketReference(Protocol):
    def reference(self, symbol: str) -> Reference: ...

    def admission(self, symbol: str) -> tuple[bool, str, str | None]: ...

    def prints_between(self, symbol: str, after_ts: float, through_ts: float) -> list[Print]: ...

    def now_ts(self) -> float: ...


class ReplayReference:
    """The Sim venue's market: ``sim.practice`` at the playhead, looked up at call time."""

    def reference(self, symbol: str) -> Reference:
        from sim import practice

        return practice.reference(symbol)

    def admission(self, symbol: str) -> tuple[bool, str, str | None]:
        from sim import practice

        return practice.admission(symbol)

    def prints_between(self, symbol: str, after_ts: float, through_ts: float) -> list[Print]:
        from sim import practice

        return practice.prints_between(symbol, after_ts, through_ts)

    def now_ts(self) -> float:
        from sim import practice

        return practice.playhead_ts()

    def replay_key(self) -> tuple | None:
        from sim import practice

        active = practice.loaded()
        return active.key if active is not None else None

    def session_close_ts(self, ts: float) -> float:
        """The replayed session's close: the session clock's window end for ``ts``."""
        from sim import session_clock

        from practice.clock import at

        return session_clock.session_bounds_on(at(ts))[1].timestamp()


def _price(value: Any) -> float | None:
    try:
        px = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return px if px is not None and px > 0 else None


def top_of_book(book: dict | None) -> tuple[float | None, float | None]:
    """Best bid / best ask of a depth-state book; ``None`` for an absent side."""
    if not book:
        return None, None
    bids = [p for p in (_price(r.get("price")) for r in book.get("bids") or []) if p is not None]
    asks = [p for p in (_price(r.get("price")) for r in book.get("asks") or []) if p is not None]
    return (max(bids) if bids else None), (min(asks) if asks else None)


class LiveReference:
    """The Paper venue's market: the live IBKR feed, with its freshness enforced."""

    def __init__(self, fresh_sec: float = PRACTICE_LIVE_FRESH_SEC) -> None:
        self.fresh_sec = float(fresh_sec)

    def now_ts(self) -> float:
        return time.time()

    def session_close_ts(self, ts: float) -> float:
        """The desk's session ends at ``PRACTICE_SESSION_CLOSE_HOUR_ET``; at or after it, the next day's."""
        from practice.order_rules import next_close_after

        return next_close_after(ts)

    def fresh_last(self, symbol: str) -> float | None:
        """The L1 last, only while its stream ticked within the freshness window."""
        from ibkr import ticks

        sym = symbol.upper()
        if not ticks.is_fresh(sym, self.fresh_sec):
            return None
        row = ticks.last_quotes([sym]).get(sym) or {}
        return _price(row.get("price"))

    def recent_print(self, symbol: str) -> float | None:
        """The newest archived print that sets a price inside the freshness window, if the symbol is watched."""
        from l2 import tape

        sym = symbol.upper()
        if not tape.is_watched(sym):
            return None
        now = self.now_ts()
        for row in reversed(tape.get_trades_in_range(sym, now - self.fresh_sec, now)):
            if not row_sets_price(row):
                continue
            px = _price(row.get("price"))
            if px is not None:
                return px
        return None

    def reference(self, symbol: str) -> Reference:
        from ibkr.depth import state as depth_state

        sym = (symbol or "").strip().upper()
        if not sym:
            return Reference(None, live=True)
        last = self.fresh_last(sym)
        if last is None:
            last = self.recent_print(sym)
        bid, ask = top_of_book(depth_state.current_book(sym))
        return Reference(last, bid, ask, live=True)

    def admission(self, symbol: str) -> tuple[bool, str, str | None]:
        sym = (symbol or "").strip().upper()
        if not sym:
            return False, "Practice orders need a symbol", PRACTICE_NO_LIVE_PRINT_CODE
        if self.reference(sym).last is None:
            return False, PRACTICE_NO_LIVE_PRINT_REASON, PRACTICE_NO_LIVE_PRINT_CODE
        return True, "OK", None

    def prints_between(self, symbol: str, after_ts: float, through_ts: float) -> list[Print]:
        """Archived prints that set a price in ``(after_ts, through_ts]`` as ``(ts, price)``, oldest first."""
        from l2 import tape

        sym = symbol.upper()
        if through_ts <= after_ts or not tape.is_watched(sym):
            return []
        out: list[Print] = []
        for row in tape.get_trades_in_range(sym, after_ts, through_ts):
            ts = row.get("ts")
            px = _price(row.get("price"))
            if ts is None or px is None or float(ts) <= after_ts or not row_sets_price(row):
                continue
            out.append((float(ts), px))
        return out


class SimReference:
    """The Sim venue's market: the live feed at the live edge, the loaded replay off it.

    ADR 020 live-edge amendment (2026-09-21 evening). Every call asks the Sim
    clock whether the playhead is *now*; at the edge the answer is Paper's
    ``LiveReference`` (any symbol with a live print, ``live_quote`` /
    ``live_print``), off it ``ReplayReference`` unchanged (``SIM_*`` refusals,
    the loaded replay at the playhead). The clock stays the Sim playhead in
    both cases -- at the edge that is wall time, so an order placed there is
    stamped like any other and unwinds like any other when the operator
    scrubs back past it.
    """

    def __init__(self, live: MarketReference | None = None, replay: ReplayReference | None = None) -> None:
        self.live: MarketReference = live if live is not None else LiveReference()
        self.replay = replay if replay is not None else ReplayReference()

    @staticmethod
    def at_live_edge() -> bool:
        from sim import session_clock

        return session_clock.live_edge()

    def _market(self) -> MarketReference:
        return self.live if self.at_live_edge() else self.replay

    def reference(self, symbol: str) -> Reference:
        return self._market().reference(symbol)

    def admission(self, symbol: str) -> tuple[bool, str, str | None]:
        return self._market().admission(symbol)

    def prints_between(self, symbol: str, after_ts: float, through_ts: float) -> list[Print]:
        return self._market().prints_between(symbol, after_ts, through_ts)

    def now_ts(self) -> float:
        """The Sim playhead, which at the live edge is the wall clock."""
        return self.replay.now_ts()

    def replay_key(self) -> tuple | None:
        return self.replay.replay_key()

    def session_close_ts(self, ts: float) -> float:
        return self.replay.session_close_ts(ts)
