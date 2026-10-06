"""What the triggers audit reads (ADR 044, ``bot.trigger_audit``): the day's eyes' journal, the bot's audit
stream, the day's hot list, each strategy's bot rules today and the settings now.

Each source answers ``{ok, error}``. One that cannot be read is said there, and every square that needs
it says so instead of guessing. Errors are the module's own words: an exception's text stays in the log.

- **The journal**: the day's ``triggered``, ``armed`` and ``scored`` lines of the templates in play
  (``playing: true``) and the ``session`` lines (Nova starting). Today's file is read as it grows
  (``eyes.journal_day.JournalTail``: appended bytes only) and only those lines are kept; another day
  is read on each ask.
- **The audit stream**: every line from the start of the day (ET) to the end of the file
  (``bot.entry_rules.audit_rows``), so a change after a trigger still tells what was set before it.
- **The hot list**: today's file (``hot_list.store.current``), else the day's kept copy
  (``hot_list.entries_on``).
- **The settings now** (``Now``): each venue's dial and the desk's Who trades switches -- what nothing
  has changed since.

Owner: this module (in memory: today's kept journal lines; invalidation: a journal read again from the
start starts again from nothing, and another date starts a new tail).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, time as dtime
from typing import Any
from zoneinfo import ZoneInfo

from constants_bot import BOT_SCANNER_SETUPS, BOT_TZ
from constants_stock_mode import STOCK_MODE_BOT, STOCK_MODE_SIGNAL

logger = logging.getLogger(__name__)
_ET = ZoneInfo(BOT_TZ)
KEPT = frozenset({"triggered", "armed", "scored", "session"})
_lock = threading.Lock()
_today: tuple[str, Any, list[dict[str, Any]]] | None = None      # (date, its tail, the lines kept)


def ok() -> dict[str, Any]:
    return {"ok": True, "error": None}


def failed(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


def day_start(day: str) -> float:
    """Midnight ET of ``day`` (epoch seconds)."""
    return datetime.combine(datetime.fromisoformat(day).date(), dtime.min, _ET).timestamp()


def _keep(line: dict[str, Any]) -> bool:
    event = line.get("event")
    return event in KEPT and (event == "session" or line.get("playing") is True)


def journal(day: str, *, today: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The day's kept journal lines, oldest first, and the source's ``{ok, error}``."""
    global _today
    from eyes import journal as eyes_journal
    from eyes.journal_day import JournalTail

    path = eyes_journal.day_path(day)
    if path is None:
        return [], failed(f"no eyes' journal on file for {day}")
    try:
        if not today:
            return [row for row in JournalTail(path, day).read() if _keep(row)], ok()
        with _lock:
            if _today is None or _today[0] != day or _today[1].path != path:
                _today = (day, JournalTail(path, day), [])
            _day, tail, kept = _today
            generation = tail.generation
            rows = tail.read()
            if tail.generation != generation:
                kept.clear()                # the file was read again from its start
            kept.extend(row for row in rows if _keep(row))
            return list(kept), ok()
    except OSError:
        logger.warning("triggers audit: the eyes' journal of %s could not be read", day, exc_info=True)
        return [], failed("the eyes' journal could not be read (the backend log has the error)")


def audit(day: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The audit lines from the start of ``day`` to the end of the file, and the source's ``{ok, error}``."""
    from bot.entry_rules import audit_rows

    try:
        return audit_rows(day), ok()
    except Exception:
        logger.warning("triggers audit: the bot's audit stream could not be read", exc_info=True)
        return [], failed("the bot's audit stream could not be read (the backend log has the error)")


def hot_list(day: str, now: float | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """``{SYMBOL: entry}`` of the day's hot list in the list's order, and the source's ``{ok, error}``.
    ``day`` is today when it is the trading day ``now`` belongs to (the list's day starts at 04:00 ET)."""
    try:
        import hot_list as listing

        if day == listing.trading_day(now):
            from hot_list.store import current

            doc, error = current(now)
            entries = None if error else list(doc.get("entries") or [])
        else:
            entries, error = listing.entries_on(day)
    except Exception:
        logger.warning("triggers audit: the hot list of %s could not be read", day, exc_info=True)
        return {}, failed("the hot list could not be read (the backend log has the error)")
    if entries is None:
        return {}, failed(str(error or f"no hot list kept for {day}"))
    listed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        sym = str((entry or {}).get("symbol") or "").strip().upper()
        if sym and sym not in listed:
            listed[sym] = entry
    return listed, ok()


def rules() -> dict[str, dict[str, Any]]:
    """Each strategy's bot rules today: ``{grades, setups_a_day, template, error, window: {start, end, open,
    error}}`` -- its template in play's (``bot.strategy_rules``, ``bot.entry_rules.window``)."""
    from bot import entry_rules, strategy_rules

    out: dict[str, dict[str, Any]] = {}
    for setup in BOT_SCANNER_SETUPS:
        win = entry_rules.window(setup)
        out[setup] = {**strategy_rules.rules(setup), "window": {k: win.get(k) for k in ("start", "end", "open",
                                                                                          "error")}}
    return out


class Now:
    """The settings now: each venue's dial (the session file) and the desk's Who trades switches."""

    def __init__(self) -> None:
        from bot.gates import current_venue
        from bot.persist import load_session

        self.row = load_session()
        self.venue = current_venue()

    def dial(self, venue: str | None) -> dict[str, Any]:
        from bot.venue_levels import dial_of

        return dial_of(self.row, venue)

    def level(self, venue: str | None, setup: str) -> int:
        from bot.setup_levels import own_levels

        return own_levels(self.dial(venue)).get(setup, 0)

    def mode(self, venue: str | None, symbol: str) -> str:
        from bot.eligibility import normalize_symbols
        from stock_mode import model, store

        sym = (symbol or "").strip().upper()
        if sym in normalize_symbols(self.dial(venue).get("symbol_allowlist")):
            return STOCK_MODE_BOT
        if venue is not None and venue == self.venue:
            sw = store.switch(sym)
            if sw:
                return model.mode_of(sw.get("buy"), sw.get("sell"))
        return STOCK_MODE_SIGNAL

    def cap(self, venue: str | None) -> int:
        from bot.sleeve import normalize

        return int(normalize(self.dial(venue).get("caps"))["entries_per_day"])


def reset_for_tests() -> None:
    global _today
    with _lock:
        _today = None
