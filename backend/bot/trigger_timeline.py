"""What the bot's audit stream says a setting was at any moment of a day (ADR 044, the squares). Pure.

The triggers audit (``bot.trigger_audit``) judges each trigger by the settings it met: each strategy's
own level, each stock's mode (Who trades) and the venue's daily cap. The stream records every change
of them with its ``from`` and ``to`` -- ``setup_level`` (``inputs: {setup, from, to}``), ``stock_mode``
``set`` (``inputs: {symbol, from, to}``) and ``caps`` (``inputs: {venue, changed: {KEY: {from,
to}}}``) -- each stamped with the venue it applied to. What a setting was at ``t`` is read from the
nearest record:

- the last change at or before ``t`` (its ``to``);
- else the first change after ``t`` (its ``from``: nothing changed it between);
- else the setting now (nothing changed it since).

A stock's mode has two more kinds of event. The 04:00 ET rollover of the hot list (a ``hot_list``
line, ``event: "rollover"``) clears every Nova Buy on every venue, so a stock reads You · You after
it. A process start (the eyes' journal's ``session`` line) and a venue change (a ``venue`` line)
drop the in-memory Auto-entry and Approve switches (ADR 037) and keep the bot list, which is
persisted. Where a record cannot say what a mode was before such an event, it is ``UNKNOWN`` --
stated, never guessed.

Owner: this module (no state).
"""
from __future__ import annotations

from typing import Any, Callable

from constants_stock_mode import STOCK_MODE_AUDIT_ACTION, STOCK_MODE_BOT, STOCK_MODE_SIGNAL

UNKNOWN = "unknown"
SET, CLEAR, RESET = "set", "clear", "reset"
_HOT_LIST = "hot_list"
Event = tuple[float, str, Any, Any]          # (ts, kind, from, to)


def _ts(row: dict[str, Any]) -> float | None:
    ts = row.get("timestamp")
    return float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else None


def _sym(raw: Any) -> str:
    return str(raw or "").strip().upper()


class Timeline:
    """The day's recorded changes, read back at any moment (``level_at``, ``mode_at``, ``cap_at``)."""

    def __init__(self, rows: list[dict[str, Any]], *, restarts: list[float] | None = None):
        self.levels: dict[tuple[str | None, str], list[Event]] = {}
        self.modes: dict[tuple[str | None, str], list[Event]] = {}
        self.caps: dict[str | None, list[Event]] = {}
        self.global_modes: list[Event] = [(float(t), RESET, None, None) for t in restarts or []]
        for row in rows:
            self._add(row)
        for table in (self.levels, self.modes, self.caps):
            for events in table.values():
                events.sort(key=lambda e: e[0])
        self.global_modes.sort(key=lambda e: e[0])

    def _add(self, row: dict[str, Any]) -> None:
        ts, action, inputs = _ts(row), row.get("action"), row.get("inputs") or {}
        if ts is None or not isinstance(inputs, dict):
            return
        venue = row.get("venue")
        if action == "setup_level" and inputs.get("setup"):
            self.levels.setdefault((venue, str(inputs["setup"])), []).append(
                (ts, SET, inputs.get("from"), inputs.get("to")))
        elif action == STOCK_MODE_AUDIT_ACTION and row.get("outcome") == "set" and inputs.get("symbol"):
            self.modes.setdefault((venue, _sym(inputs["symbol"])), []).append(
                (ts, SET, inputs.get("from"), inputs.get("to")))
        elif action == _HOT_LIST and (inputs.get("event") == "rollover" or row.get("outcome") == "rollover"):
            self.global_modes.append((ts, CLEAR, None, STOCK_MODE_SIGNAL))
        elif action == "venue":
            self.global_modes.append((ts, RESET, None, None))
        elif action == "caps":
            entry = (inputs.get("changed") or {}).get("entries_per_day")
            if isinstance(entry, dict):
                self.caps.setdefault(inputs.get("venue") or venue, []).append(
                    (ts, SET, entry.get("from"), entry.get("to")))

    # -- reads ---------------------------------------------------------------------------
    def level_at(self, venue: str | None, setup: str, t: float, now: Callable[[], Any]) -> Any:
        """A strategy's own level (0 Off, 1 Eyes, 2 On) on ``venue`` at ``t``; ``now()`` is today's."""
        return nearest(self.levels.get((venue, setup), []), t, now)

    def cap_at(self, venue: str | None, t: float, now: Callable[[], Any]) -> Any:
        """The venue sleeve's ``entries_per_day`` at ``t``."""
        return nearest(self.caps.get(venue, []), t, now)

    def mode_at(self, venue: str | None, symbol: str, t: float, now: Callable[[], Any]) -> Any:
        """A stock's mode (``signal`` | ``approve`` | ``auto_entry`` | ``bot``) on ``venue`` at ``t``, or ``UNKNOWN``."""
        events = sorted(self.modes.get((venue, _sym(symbol)), []) + self.global_modes, key=lambda e: e[0])
        dropped = False
        for _at, kind, _frm, to in reversed([e for e in events if e[0] <= t]):
            if kind == SET:
                return _dropped(to) if dropped else to
            if kind == CLEAR:
                return STOCK_MODE_SIGNAL
            dropped = True                  # a restart or a venue change after the last record
        return _before([e for e in events if e[0] > t], now)


def nearest(events: list[Event], t: float, now: Callable[[], Any]) -> Any:
    """The value at ``t`` from the nearest record: the last ``to`` at or before it, else the first ``from``
    after it, else ``now()``."""
    prior = [e for e in events if e[0] <= t]
    if prior:
        return prior[-1][3]
    later = [e for e in events if e[0] > t]
    return later[0][2] if later else now()


def _dropped(mode: Any) -> Any:
    """What a restart or a venue change leaves of a mode: the bot list stays, a switch is gone."""
    return STOCK_MODE_BOT if mode == STOCK_MODE_BOT else STOCK_MODE_SIGNAL


def _before(later: list[Event], now: Callable[[], Any]) -> Any:
    """The mode just before the first of ``later`` (``now()`` when there is none)."""
    if not later:
        return now()
    _at, kind, frm, _to = later[0]
    if kind == SET:
        return frm
    if kind == CLEAR:
        return UNKNOWN                      # a rollover forgets what was set before it
    after = _before(later[1:], now)         # a restart or a venue change keeps only the bot list
    return STOCK_MODE_BOT if after == STOCK_MODE_BOT else UNKNOWN
