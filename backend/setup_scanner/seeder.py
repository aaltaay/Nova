"""Today's minutes for a symbol the setup scanner starts following (ADR 022).

The day so far is seeded from the bar store (``hooks.default_seed``). The store holds a symbol's
minutes only once something fetched them (a chart) or Nova's Level 1 line built them
(``ibkr/l1_minute``), so a name HOD Momo admits mid-morning had nothing before its line opened and
every lane warmed up from scratch: AMOD, followed at 07:51:22 on 2026-10-02 after trading since
04:00, wrote its first first-pullback line at 08:23 -- 32 bars later -- and its 5-minute lane still
read "warming up (17/32 bars)" at 09:19.

Now a seed whose stored minutes start more than ``SETUPS_SEED_LATE_START_SEC`` after 04:00 (or that
holds none) keeps the symbol ``seeding`` (the board says so) and queues it for IBKR's 1-minute history
of today. One
symbol is asked at a time; the history hook paces the requests against IBKR's budget
(``hooks.live_history``). When the history lands the symbol is seeded from the store again, so the
lanes see the day from 04:00. Minutes the Level 1 line built since the symbol was followed keep their
place: ``MinuteBars.seed`` takes only stored minutes older than the first live one, so no minute
counts twice. A history that does not come is given up (``SETUPS_SEED_HISTORY_MAX_TRIES`` unanswered
asks, or ``SETUPS_SEED_HISTORY_MAX_WAIT_SEC``), and the symbol is seeded with what the store has, as
before. A name that leaves the followed set keeps its place in the queue for a while: the HOD Momo
set churns at its edge (8,702 watch changes on 2026-10-01), and a name is often back seconds later.

Only the start of the day is waited for. A hole later in the day (a line closed for a while) is seeded
as it is: the store cannot tell a quiet stretch from a missed one, and waiting would hold a name whose
lanes are warm out of the open's busiest minutes while the queue drains.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time as dtime
from typing import Any, Awaitable, Callable, Iterable
from zoneinfo import ZoneInfo

from constants import IBKR_HISTORICAL_PACE_MAX
from constants_setups import (
    SETUPS_SEED_HISTORY_BUDGET,
    SETUPS_SEED_HISTORY_FAILED_RETRY_SEC,
    SETUPS_SEED_HISTORY_MAX_TRIES,
    SETUPS_SEED_HISTORY_MAX_WAIT_SEC,
    SETUPS_SEED_HISTORY_RETRY_SEC,
    SETUPS_SEED_HISTORY_SPACING_SEC,
    SETUPS_SEED_LATE_START_SEC,
)
from setup_scanner.bars import Bar

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# What a history ask came to (the hook's answer, with a reason or None).
SEED_FILLED = "filled"      # IBKR's minutes of today are in the store
SEED_COVERED = "covered"    # they already were: nothing was asked
SEED_SHED = "shed"          # not now (IBKR's budget, a loading chart, IBKR not ready): ask again soon
SEED_FAILED = "failed"      # IBKR did not answer, or answered an error

History = Callable[[str, float], Awaitable[tuple[str, str | None]]]


def session_start_ts(now: float) -> float:
    """04:00 ET of ``now``'s date: where the scanner's day, and every seed, begins."""
    d = datetime.fromtimestamp(now, ET).date()
    return datetime.combine(d, dtime(4, 0), ET).timestamp()


def late_start(bars: Iterable[Bar], since: float, now: float) -> float:
    """Seconds from ``since`` to the first stored minute (to ``now`` when none is stored), never below 0."""
    first = min((b.t for b in bars), default=now)
    return max(0.0, min(first, now) - since)


def send_wait(now: float, last_send: float, window_used: int, chart_loading: bool) -> str | None:
    """Why the scanner's next history request must wait, or ``None`` to send it now.

    One request every ``SETUPS_SEED_HISTORY_SPACING_SEC`` at most, never while a chart's own history
    is loading, and only while IBKR's 10-minute window keeps room for the charts: following several
    names at once never bursts IBKR's historical budget.
    """
    if chart_loading:
        return "a chart's history is loading first"
    if now - last_send < SETUPS_SEED_HISTORY_SPACING_SEC:
        return f"the scanner asked {now - last_send:.0f}s ago"
    if window_used >= SETUPS_SEED_HISTORY_BUDGET:
        return (f"{window_used} of IBKR's {IBKR_HISTORICAL_PACE_MAX} historical requests in 10 minutes "
                "are used: the rest are the charts'")
    return None


@dataclass
class _Wait:
    since: float              # when the seed first came back short
    due: float                # when it may be asked next
    tries: int = 0            # asks IBKR did not answer
    last: str | None = None   # the last ask's reason, for the logs


class Seeder:
    """Seeds each symbol the engine starts following; asks IBKR's history first when the store is short.

    ``host`` is the engine: ``bars``, ``seeding``, ``lanes``, ``in_session`` and ``clock``. ``read`` is
    the seed hook, ``(symbol, 04:00) -> stored minutes``; ``history`` the history hook (``None``: seed
    with what the store has, as tests and replays do).
    """

    def __init__(self, host: Any, read: Callable[[str, float], list[Bar]], history: History | None):
        self.host, self.read, self.history = host, read, history
        self.waiting: dict[str, _Wait] = {}
        self.task: asyncio.Future | None = None
        self.gen = 0          # a new session forgets every ask of the old one

    def clear(self) -> None:
        self.waiting.clear()
        self.task = None
        self.gen += 1

    async def seed(self, sym: str, now: float) -> None:
        since = session_start_ts(now)
        bars = await self._read(sym, since)
        late = late_start(bars, since, now)
        if self.history is not None and self.host.in_session(now) and late > SETUPS_SEED_LATE_START_SEC:
            if sym not in self.waiting:
                self.waiting[sym] = _Wait(since=now, due=now)
                logger.info("setup scanner: %s's stored minutes start %.0f min after 04:00 -- "
                            "asking IBKR for its 1-minute history before seeding", sym, late / 60)
            return
        self.finish(sym, bars, now)

    async def step(self, now: float) -> None:
        """Each tick: give up what waited too long, then ask for the next followed symbol's history."""
        if self.task is not None:
            if not self.task.done():
                return
            self.task = None
        closed = not self.host.in_session(now)
        for sym, w in list(self.waiting.items()):
            if closed or now - w.since >= SETUPS_SEED_HISTORY_MAX_WAIT_SEC:
                del self.waiting[sym]
                why = "the session closed" if closed else (
                    f"no history within {SETUPS_SEED_HISTORY_MAX_WAIT_SEC / 60:.0f} min ({w.last or 'its turn never came'})")
                await self._settle(sym, now, why)
        ready = [(w.since, s) for s, w in self.waiting.items() if w.due <= now and s in self.host.bars]
        if ready:                  # oldest first; a name that left keeps its place for when it is back
            due = min(ready)[1]
            self.task = asyncio.ensure_future(self._ask(due, self.waiting[due], self.gen))

    async def _ask(self, sym: str, w: _Wait, gen: int) -> None:
        try:
            outcome, detail = await self.history(sym, session_start_ts(w.since))
        except Exception as exc:   # the hook states its own failures; this is one it did not expect
            logger.warning("setup scanner: the history ask for %s failed", sym, exc_info=True)
            outcome, detail = SEED_FAILED, str(exc) or type(exc).__name__
        if gen != self.gen or self.waiting.get(sym) is not w:
            return                 # a new session, or the wait was given up meanwhile
        now = self.host.clock()
        w.last = detail
        if outcome in (SEED_FILLED, SEED_COVERED):
            del self.waiting[sym]
            await self._settle(sym, now, None)
        elif outcome == SEED_FAILED:
            w.tries += 1
            w.due = now + SETUPS_SEED_HISTORY_FAILED_RETRY_SEC
            if w.tries >= SETUPS_SEED_HISTORY_MAX_TRIES:
                del self.waiting[sym]
                await self._settle(sym, now, f"IBKR did not answer {w.tries} times ({detail})")
        else:
            w.due = now + SETUPS_SEED_HISTORY_RETRY_SEC

    async def _settle(self, sym: str, now: float, why: str | None) -> None:
        """Seed a symbol still followed and still seeding from the store as it is now."""
        mb = self.host.bars.get(sym)
        if mb is None or sym not in self.host.seeding:
            return
        gen = self.gen
        bars = await self._read(sym, session_start_ts(now))
        if gen != self.gen or self.host.bars.get(sym) is not mb or sym not in self.host.seeding:
            return                 # rolled over, dropped, or seeded by a fresh follow meanwhile
        if why:
            logger.warning("setup scanner: %s seeded without IBKR's history -- %s; its lanes warm up "
                           "from what the store has", sym, why)
        else:
            logger.info("setup scanner: %s seeded with %d stored minutes after IBKR's history", sym, len(bars))
        self.finish(sym, bars, now)

    def finish(self, sym: str, bars: list[Bar], now: float) -> None:
        mb = self.host.bars.get(sym)
        self.host.seeding.discard(sym)
        if mb is None:
            return
        mb.seed([b for b in bars if self.host.in_session(b.t)])
        for lane in self.host.lanes:
            lane.on_bars(sym, mb.completed, now)

    async def _read(self, sym: str, since: float) -> list[Bar]:
        try:
            return await asyncio.to_thread(self.read, sym, since)
        except Exception:  # maintainer: allow-swallow logged; an unreadable store seeds nothing and the lanes warm up live
            logger.warning("setup scanner: could not seed %s from the bar store", sym, exc_info=True)
            return []
