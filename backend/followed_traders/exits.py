"""The tape at each closed trade's exit, read from IBKR's history in the background and kept.

The same read answers the tape at an entry whose ticker the feed may have read glued to its price (``tickers``): the
tape for one symbol at one time is the same fact, whichever trade asks.

``view`` answers what is known now (``pending`` until read) and remembers the exit as wanted; ``pump`` sends the
next wanted read when none is in flight. One read at a time, on the IB loop (``spawn_ib``), through IBKR's
historical budget with ``FOLLOWED_EXIT_HEADROOM`` left for charts (``ibkr.historical_trades``):

- a point exit is the last price-setting trade at or before ``exit_ts``;
- a window exit (``exit_since_ts`` set) is the low and high of the price-setting trades in the window, or, when
  the window holds more than ``FOLLOWED_EXIT_MAX_PAGES`` pages of trades, of IBKR's 1-minute bars over the
  minutes that overlap it (today's, from the chart's store: ``historical_service.request_bars``).

The newest exit is read first, so today's come before a record's history. Shed by pacing or an open chart, a read
is asked again after ``FOLLOWED_EXIT_RETRY_SEC``; failed, after ``FOLLOWED_EXIT_FAIL_RETRY_SEC``, and after
``FOLLOWED_EXIT_MAX_TRIES`` failures it reads ``unavailable`` until the process restarts. A ticker IBKR does not know
reads ``unavailable`` with ``FOLLOWED_NO_SUCH_TICKER`` at once: asking again would not make one.

Persisted: ``followed-exits.json`` in the operator cache (``FOLLOWED_EXITS_FILE``), every exit read as one price
(``at``) or a range (``range``), so a past day's exit is asked of IBKR once. Owner: this module (reads it on first
use, writes it after each such read). Invalidation: none by time -- an exit's tape is a fixed fact -- only a
``schema_version`` bump; an unknown version is refused loud and never overwritten.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from followed_traders import pricing
from followed_traders.constants_followed import (
    FOLLOWED_EXIT_BARS_LIMIT,
    FOLLOWED_EXIT_FAIL_RETRY_SEC,
    FOLLOWED_EXITS_FILE,
    FOLLOWED_EXITS_SCHEMA_VERSION,
    FOLLOWED_EXIT_HEADROOM,
    FOLLOWED_EXIT_LOOKBACK_SEC,
    FOLLOWED_EXIT_MAX_PAGES,
    FOLLOWED_EXIT_MAX_TRIES,
    FOLLOWED_EXIT_PAGE_TIMEOUT_SEC,
    FOLLOWED_EXIT_RETRY_SEC,
    FOLLOWED_NO_SUCH_TICKER,
)

logger = logging.getLogger(__name__)
Key = tuple[str, float, float | None]          # (symbol, exit_ts, exit_since_ts)

_lock = threading.Lock()
_results: dict[Key, dict[str, Any]] = {}       # read: the stated exit, kept
_wanted: dict[Key, dict[str, Any]] = {}        # not read yet: {next_try, fails, why}
_in_flight: Key | None = None
_clock: Callable[[], float] = time.time
_loaded = False
_refused = False                               # the file on disk has a version this code does not read
KEPT = ("at", "range")                         # the results written to disk


def reset_for_tests() -> None:
    global _in_flight, _loaded, _refused
    with _lock:
        _results.clear()
        _wanted.clear()
        _in_flight = None
        _loaded, _refused = False, False


def _path() -> Path:
    from paths import cache_dir

    return cache_dir() / FOLLOWED_EXITS_FILE


def _key_of(row: dict[str, Any]) -> Key:
    since = row.get("exit_since_ts")
    return (str(row["symbol"]), float(row["exit_ts"]), None if since is None else float(since))


def _load_locked() -> None:
    """Read the kept exits once (the caller holds ``_lock``)."""
    global _loaded, _refused
    if _loaded:
        return
    _loaded = True
    path = _path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _refused = True
        logger.exception("followed traders: %s could not be read (%s); exits are read again and not kept", path, exc)
        return
    if not isinstance(payload, dict) or payload.get("schema_version") != FOLLOWED_EXITS_SCHEMA_VERSION:
        _refused = True
        logger.error("followed traders: %s has schema_version %r, not %s; refused, not overwritten", path,
                     payload.get("schema_version") if isinstance(payload, dict) else None,
                     FOLLOWED_EXITS_SCHEMA_VERSION)
        return
    for row in payload.get("exits") or []:
        try:
            exit_ = row["exit"]
            if exit_["state"] in KEPT:
                _results[_key_of(row)] = stated(**exit_)
        except (KeyError, TypeError, ValueError):  # one bad row is skipped, the rest are kept
            logger.warning("followed traders: skipped an unreadable kept exit %r", row)


def _save_locked() -> None:
    """Write every kept exit (the caller holds ``_lock``); a refused file is never overwritten."""
    if _refused:
        return
    rows = [{"symbol": k[0], "exit_ts": k[1], "exit_since_ts": k[2], "exit": v}
            for k, v in _results.items() if v["state"] in KEPT]
    path = _path()
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"schema_version": FOLLOWED_EXITS_SCHEMA_VERSION, "exits": rows}, f)
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("followed traders: kept exits not written to %s: %s", path, exc)


def stated(state: str, *, price: float | None = None, low: float | None = None, high: float | None = None,
           from_ts: float | None = None, to_ts: float | None = None, trade_ts: float | None = None,
           source: str | None = None, why: str | None = None) -> dict[str, Any]:
    return {"state": state, "price": price, "low": low, "high": high, "from_ts": from_ts, "to_ts": to_ts,
            "trade_ts": trade_ts, "source": source, "why": why}


def view(symbol: str, exit_ts: float, exit_since_ts: float | None, now: float) -> dict[str, Any]:
    """The exit as known now; an exit not read yet is remembered as wanted and reads ``pending``."""
    key: Key = (symbol, exit_ts, exit_since_ts)
    with _lock:
        _load_locked()
        got = _results.get(key)
        if got is not None:
            return got
        want = _wanted.setdefault(key, {"next_try": now, "fails": 0, "why": None})
        return stated("pending", from_ts=exit_since_ts, to_ts=exit_ts, why=want["why"])


def pump(now: float, *, ibkr_ready: bool, spawn: Callable[[str, Callable[[], Any]], None] | None = None) -> None:
    """Send the next wanted read that is due, when none is in flight and IBKR is ready."""
    global _in_flight
    with _lock:
        if _in_flight is not None or not ibkr_ready:
            return
        due = [k for k, w in _wanted.items() if w["next_try"] <= now]
        if not due:
            return
        key = max(due, key=lambda k: k[1])          # the newest exit first: today's before a record's history
        _in_flight = key
    try:
        (spawn or _spawn_ib)(f"followed.exit.{key[0]}", lambda: _job(key))
    except RuntimeError as exc:                      # the IB loop is not running
        _finish(key, "failed", f"IBKR's connection is not running ({exc})")


def _spawn_ib(name: str, factory: Callable[[], Any]) -> None:
    from ibkr.loop_supervisor import spawn_ib

    spawn_ib(name, factory)


async def _job(key: Key) -> None:
    from ibkr.historical_service import HistoricalShed
    from ibkr.historical_trades import UnknownContract

    try:
        result = await read(key)
    except HistoricalShed as exc:
        _finish(key, "shed", str(exc))
    except UnknownContract:
        _finish(key, "done", stated("unavailable", from_ts=key[2], to_ts=key[1], why=FOLLOWED_NO_SUCH_TICKER))
    except Exception as exc:  # any IBKR failure: stated on the row and asked again later
        logger.warning("followed traders: the exit of %s at %s could not be read: %s", key[0], key[1], exc)
        _finish(key, "failed", f"{type(exc).__name__}: {exc}")
    else:
        _finish(key, "done", result)


async def read(key: Key) -> dict[str, Any]:
    """Read one exit from IBKR (on the IB loop); raises ``HistoricalShed`` or the IBKR error."""
    from ibkr import historical_trades

    symbol, exit_ts, since = key
    end = float(int(exit_ts)) + 1.0                  # IBKR's trades of exit_ts's own second count
    if since is None:
        got = await historical_trades.recent_trades(
            symbol, end, FOLLOWED_EXIT_LOOKBACK_SEC, max_pages=1, headroom=FOLLOWED_EXIT_HEADROOM,
            timeout=FOLLOWED_EXIT_PAGE_TIMEOUT_SEC)
        hit = pricing.exit_at(got["trades"], exit_ts)
        if hit is None:
            return stated("unavailable", to_ts=exit_ts,
                          why=f"no IBKR trade in the {FOLLOWED_EXIT_LOOKBACK_SEC / 60:.0f} minutes before the exit")
        return stated("at", price=hit["price"], trade_ts=hit["trade_ts"], to_ts=exit_ts, source="ibkr_trades")
    # recent_trades keeps trades after its start, so start a second early to keep since's own second.
    got = await historical_trades.recent_trades(
        symbol, end, end - float(int(since)) + 1.0, max_pages=FOLLOWED_EXIT_MAX_PAGES,
        headroom=FOLLOWED_EXIT_HEADROOM, timeout=FOLLOWED_EXIT_PAGE_TIMEOUT_SEC)
    if got["complete"]:
        span = pricing.range_from_trades(got["trades"], since, exit_ts)
        if span is None:
            return stated("unavailable", from_ts=since, to_ts=exit_ts, why="no IBKR trade in the exit's window")
        return stated("range", low=span[0], high=span[1], from_ts=since, to_ts=exit_ts, source="ibkr_trades")
    span = await _bars_range(symbol, since, exit_ts)
    if span is None:
        return stated("unavailable", from_ts=since, to_ts=exit_ts,
                      why=f"more than {FOLLOWED_EXIT_MAX_PAGES * 1000:,} trades in the window and no 1-minute bars "
                          "cover it")
    return stated("range", low=span[0], high=span[1], from_ts=since, to_ts=exit_ts, source="ibkr_1min_bars")


async def _bars_range(symbol: str, since: float, exit_ts: float) -> tuple[float, float] | None:
    from ibkr import historical_service

    got = await historical_service.request_bars(symbol, "1Min", FOLLOWED_EXIT_BARS_LIMIT, priority="background")
    return pricing.range_from_bars(list((got or {}).get("bars") or []), since, exit_ts)


def _finish(key: Key, outcome: str, value: Any) -> None:
    global _in_flight
    now = _clock()
    with _lock:
        if _in_flight == key:
            _in_flight = None
        want = _wanted.get(key)
        if want is None:
            return
        if outcome == "done":
            _results[key] = value
            del _wanted[key]
            if value["state"] in KEPT:
                _save_locked()
        elif outcome == "shed":
            want.update(next_try=now + FOLLOWED_EXIT_RETRY_SEC, why=f"waiting for IBKR's history ({value})")
        else:
            want["fails"] += 1
            if want["fails"] >= FOLLOWED_EXIT_MAX_TRIES:
                _results[key] = stated("unavailable", from_ts=key[2], to_ts=key[1],
                                       why=f"IBKR's history did not answer {want['fails']} times ({value})")
                del _wanted[key]
            else:
                want.update(next_try=now + FOLLOWED_EXIT_FAIL_RETRY_SEC, why=f"asking IBKR again ({value})")
