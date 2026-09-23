"""The borrow feed (ADR 028): IBKR's short-stock file, polled and recorded as it changes.

IBKR publishes, for every US symbol it can lend, the shares available and the annual fee and rebate in
one public file refreshed about every 15 minutes. Polled every ``MOVE_BORROW_POLL_SEC`` (network off the
event loop); a poll that did not read the whole file (its ``#EOF`` count) is not recorded, so a partial
download never reads as "nothing to lend". Each complete poll writes only the symbols whose listing, fee
or availability changed (``move_reason/borrow_store.py``), so a restart keeps the day.

``view`` answers one symbol for the "Why it's moving" read: now, at the day's first poll (04:00 ET on),
at the last poll before it, and the day's highest fee and lowest availability. Always on;
``NOVA_BORROW_FEED=0`` turns it off.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, time as dtime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from constants_move_reason import (
    MOVE_BORROW_FEED_ENV,
    MOVE_BORROW_HTTP_TIMEOUT_SEC,
    MOVE_BORROW_POLL_SEC,
    MOVE_BORROW_RETENTION_DAYS,
    MOVE_BORROW_RETRY_SEC,
    MOVE_BORROW_URL,
    MOVE_DAY_START_HOUR_ET,
)
from move_reason import borrow_parse, borrow_store

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
Fetch = Callable[[], bytes]


def _default_fetch() -> bytes:
    with urllib.request.urlopen(MOVE_BORROW_URL, timeout=MOVE_BORROW_HTTP_TIMEOUT_SEC) as resp:
        return resp.read()


def enabled() -> bool:
    return (os.environ.get(MOVE_BORROW_FEED_ENV) or "1").strip() != "0"


def day_start(now: float) -> float:
    """04:00 ET of ``now``'s Eastern date: the "open" snapshot is the first poll at or after it."""
    day = datetime.fromtimestamp(now, ET).date()
    return datetime.combine(day, dtime(MOVE_DAY_START_HOUR_ET, 0), ET).timestamp()


def _same(a: dict[str, Any] | None, b: dict[str, Any]) -> bool:
    return a is not None and all(a.get(k) == b.get(k) for k in ("listed", "fee_rate", "available", "capped"))


class BorrowFeed:
    def __init__(self, *, fetch: Fetch = _default_fetch, clock: Callable[[], float] = time.time, db: Any = None):
        self._fetch, self._clock, self._db = fetch, clock, db
        self._lock = threading.Lock()
        self._last: dict[str, dict[str, Any]] = {}
        self._pruned_day: str | None = None
        self.since: float | None = None
        self.last_poll: float | None = None
        self.last_file_ts: float | None = None
        self.last_ok: float | None = None
        self.last_error: str | None = None
        self.polls = 0
        self.started: float | None = None

    # -- the loop ----------------------------------------------------------------------------------
    async def run(self) -> None:
        if not enabled():
            logger.info("borrow feed: off (%s=0)", MOVE_BORROW_FEED_ENV)
            return
        await asyncio.to_thread(self.warm_start)
        while True:
            ok = await asyncio.to_thread(self.poll_once)
            await asyncio.sleep(MOVE_BORROW_POLL_SEC if ok else MOVE_BORROW_RETRY_SEC)

    def warm_start(self) -> None:
        try:
            if self._db is None:
                self._db = borrow_store.connect()
            with self._lock:
                self._last = borrow_store.last_values(self._db)
                self.since = borrow_store.first_poll(self._db)
                last = borrow_store.last_poll(self._db)
                if last:
                    self.last_poll, self.last_file_ts = last
        except Exception as exc:  # noqa: BLE001 -- the read says "unknown"; the error is shown in diagnostics
            self.last_error = f"store: {exc}"[:300]
            logger.exception("borrow feed: store unavailable")
        self.started = self._clock()

    def poll_once(self) -> bool:
        now = self._clock()
        try:
            parsed = borrow_parse.parse(self._fetch())
            if not parsed.complete or not parsed.rows:
                raise ValueError(f"incomplete file ({len(parsed.rows)} rows read)")
            with self._lock:
                changes = [(sym, v) for sym, v in self._values(parsed).items() if not _same(self._last.get(sym), v)]
                if self._db is not None:
                    borrow_store.put_poll(self._db, now, parsed.file_ts, len(parsed.rows), changes)
                    self._prune(now)
                self._last.update(dict(changes))
                self.since = self.since or now
                self.last_poll, self.last_file_ts = now, parsed.file_ts
                self.last_ok, self.last_error = now, None
                self.polls += 1
            return True
        except Exception as exc:  # noqa: BLE001 -- one failed poll never stops the feed; it retries sooner
            self.last_error = str(exc)[:300]
            logger.warning("borrow feed: poll failed: %s", exc)
            return False

    def _values(self, parsed: borrow_parse.BorrowFile) -> dict[str, dict[str, Any]]:
        """Caller holds ``_lock``. This file's value for every symbol it lists or the store had listed."""
        out = {sym: {"listed": True, "fee_rate": r.fee_rate, "rebate_rate": r.rebate_rate,
                     "available": r.available, "capped": r.capped} for sym, r in parsed.rows.items()}
        for sym, prev in self._last.items():
            if sym not in out and prev.get("listed"):
                out[sym] = {"listed": False, "fee_rate": None, "rebate_rate": None, "available": None, "capped": False}
        return out

    def _prune(self, now: float) -> None:
        day = datetime.fromtimestamp(now, ET).date().isoformat()
        if self._pruned_day == day:
            return
        self._pruned_day = day
        try:
            borrow_store.prune(self._db, now - MOVE_BORROW_RETENTION_DAYS * 86400)
        except Exception:  # noqa: BLE001 -- the next day tries again; the data is still right
            logger.warning("borrow feed: prune failed", exc_info=True)

    # -- reads (any thread) ------------------------------------------------------------------------
    def view(self, symbol: str, now: float | None = None) -> dict[str, Any] | None:
        """The symbol's borrow facts, or None while nothing was recorded (unknown, never "nothing to lend")."""
        now = self._clock() if now is None else now
        sym = (symbol or "").strip().upper()
        with self._lock:
            if self.last_poll is None:
                return None
            cur = self._last.get(sym) or {"listed": False, "fee_rate": None, "rebate_rate": None,
                                          "available": None, "capped": False}
            start = day_start(now)
            open_ts = prior = opened = before = None
            today: list[dict[str, Any]] = []
            if self._db is not None:  # without the store only the latest poll is known (diagnostics says why)
                try:
                    open_ts = borrow_store.first_poll(self._db, at_or_after=start)
                    prior = borrow_store.last_poll(self._db, before=start)
                    opened = borrow_store.value_at(self._db, sym, open_ts) if open_ts is not None else None
                    before = borrow_store.value_at(self._db, sym, prior[0]) if prior else None
                    today = ([opened] if opened else []) + (
                        borrow_store.changes_between(self._db, sym, open_ts, now) if open_ts is not None else [])
                except Exception:  # noqa: BLE001 -- the history is unknown; the latest poll still answers
                    logger.warning("borrow feed: history read failed for %s", sym, exc_info=True)
                    open_ts = prior = opened = before = None
                    today = []
        fees = [r["fee_rate"] for r in today if r.get("listed") and r.get("fee_rate") is not None]
        avail = [0 if not r.get("listed") else r.get("available") for r in today]
        avail = [a for a in avail if a is not None]
        return {
            "listed": bool(cur.get("listed")), "fee_rate": cur.get("fee_rate"), "rebate_rate": cur.get("rebate_rate"),
            "available": cur.get("available"), "available_capped": bool(cur.get("capped")),
            "as_of": self.last_file_ts or self.last_poll, "since": self.since,
            "open": _snapshot(opened, open_ts), "prior": _snapshot(before, prior[0] if prior else None),
            "max_fee_today": max(fees) if fees else None, "min_available_today": min(avail) if avail else None,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"enabled": enabled(), "running": self.started is not None, "since": self.since,
                    "last_poll": self.last_poll, "file_ts": self.last_file_ts, "last_ok": self.last_ok,
                    "last_error": self.last_error, "polls": self.polls, "symbols": len(self._last),
                    "store": str(borrow_store.path())}


def _snapshot(value: dict[str, Any] | None, ts: float | None) -> dict[str, Any] | None:
    if value is None or ts is None:
        return None
    return {"listed": bool(value.get("listed")), "fee_rate": value.get("fee_rate"),
            "available": value.get("available"), "as_of": ts}


_feed: BorrowFeed | None = None


def get_feed() -> BorrowFeed:
    global _feed
    if _feed is None:
        _feed = BorrowFeed()
    return _feed


async def run() -> None:
    """Background task entry (``app_runtime_tasks``)."""
    await get_feed().run()
