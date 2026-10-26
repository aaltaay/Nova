"""What a build of a rebuilt day's Gappers by the second reads: the stored rebuilt day, the day's Massive minute file,
the prior close of a stock the store never held, and each candidate's trades (ADR 023 amendment 2026-10-13).

Read-only on every source. The one thing a read may write is the trades file's seek index (``ensure_index``), the
file ``sim/massive_index`` owns, under its own cross-process lock -- a bulk index build that holds it is waited
for, never duplicated.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from pathlib import Path

from constants_leaderboard import (
    LEADERBOARD_BOARD_GAPPERS,
    LEADERBOARD_GAPPERS_FREEZE_MIN_ET,
    LEADERBOARD_RECORD_END_MIN_ET,
    LEADERBOARD_RECORD_START_MIN_ET,
    LEADERBOARD_SECONDS_INDEX_POLL_SEC,
    LEADERBOARD_SECONDS_INDEX_WAIT_SEC,
    LEADERBOARD_SECONDS_LOGIC_VERSION,
    LEADERBOARD_SECONDS_UNIVERSE_TYPES,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_SOURCE_RECORDED,
)
from constants_sim import SIM_MASSIVE_DAYS, SIM_MASSIVE_DROPPED_CORRECTIONS, SIM_MASSIVE_MINUTES, SIM_MASSIVE_TRADES
from leaderboard import store as board_store
from leaderboard.rows import ET
from leaderboard.seconds.build import Bar, Print
from sim import massive_daily, massive_files, massive_index

logger = logging.getLogger(__name__)
# How far back the session before a day is looked for (a long holiday weekend is four days).
_PRIOR_SESSION_LOOKBACK_DAYS = 14


def _et(day: str, minutes: int) -> int:
    midnight = datetime.combine(date_cls.fromisoformat(day), time_cls(0, 0), tzinfo=ET)
    return int(midnight.timestamp()) + minutes * 60


def premarket_minutes(day: str) -> range:
    """The minutes whose seconds rank the live rule: 04:01 .. 09:29 (04:01 is the first rebuilt board)."""
    return range(_et(day, LEADERBOARD_RECORD_START_MIN_ET) + 60, _et(day, LEADERBOARD_GAPPERS_FREEZE_MIN_ET), 60)


def frozen_minutes(day: str) -> range:
    """The minutes of the frozen list: 09:30 .. 20:00."""
    return range(_et(day, LEADERBOARD_GAPPERS_FREEZE_MIN_ET), _et(day, LEADERBOARD_RECORD_END_MIN_ET) + 60, 60)


def freeze_ts(day: str) -> int:
    return _et(day, LEADERBOARD_GAPPERS_FREEZE_MIN_ET)


@dataclass
class StoredDay:
    """The rebuilt day as the leaderboard store holds it."""

    prev_close: dict[str, float]                         # every stock the store holds that day, any board
    gappers: dict[int, list[str]] = field(default_factory=dict)   # premarket minute -> symbols in rank order
    frozen: list[tuple[str, int]] = field(default_factory=list)   # the 09:30 members and their ranks
    fingerprint: str = ""


def _gappers_where(day: str) -> tuple[str, tuple]:
    return ("session_date = ? AND source = ? AND board = ?",
            (day, LEADERBOARD_SOURCE_RECONSTRUCTED, LEADERBOARD_BOARD_GAPPERS))


def fingerprint(db, day: str) -> str | None:
    """A digest of everything a build reads from the stored rebuilt day: every Gappers row (minute, symbol, rank,
    price, volume, prior close) and every stored stock's prior close, behind the build logic's version
    (``LEADERBOARD_SECONDS_LOGIC_VERSION``, so a day built by older code reads stale); None when the day has no
    rebuilt Gappers. About a second on a five-year store (2026-09-01: 13,715 Gappers rows, 1,023 stocks)."""
    where, args = _gappers_where(day)
    digest = hashlib.sha256()
    found = False
    for row in db.execute(f"SELECT minute_ts, symbol, rank, price, volume, prev_close FROM rows WHERE {where}"
                          " ORDER BY minute_ts, symbol", args):
        found = True
        digest.update(repr(tuple(row)).encode())
    if not found:
        return None
    digest.update(b"|prior closes|")
    for row in db.execute("SELECT DISTINCT symbol, prev_close FROM rows WHERE session_date = ? AND source = ?"
                          " ORDER BY symbol, prev_close", (day, LEADERBOARD_SOURCE_RECONSTRUCTED)):
        digest.update(repr(tuple(row)).encode())
    return f"{LEADERBOARD_SECONDS_LOGIC_VERSION}:{digest.hexdigest()}"


def day_sources(db, day: str) -> set[str]:
    """Which sources the store holds for the day (``recorded`` / ``reconstructed``)."""
    rows = db.execute("SELECT DISTINCT source FROM coverage WHERE session_date = ?", (day,)).fetchall()
    return {str(row[0]) for row in rows}


def stored_day(day: str, database: Path | None = None) -> StoredDay | None:
    """The day's rebuilt Gappers board and every stored prior close; None when the store holds no rebuilt Gappers."""
    db = board_store.read_only(database)
    if db is None:
        return None
    try:
        mark = fingerprint(db, day)
        if mark is None:
            return None
        prev = {str(symbol): float(close) for symbol, close in db.execute(
            "SELECT symbol, prev_close FROM rows WHERE session_date = ? AND source = ? AND prev_close > 0"
            " GROUP BY symbol", (day, LEADERBOARD_SOURCE_RECONSTRUCTED)).fetchall()}
        where, args = _gappers_where(day)
        freeze = freeze_ts(day)
        out = StoredDay(prev_close=prev, fingerprint=mark)
        for minute, symbol, rank in db.execute(
                f"SELECT minute_ts, symbol, rank FROM rows WHERE {where} ORDER BY minute_ts, rank", args):
            if minute < freeze:
                out.gappers.setdefault(int(minute), []).append(str(symbol))
            elif minute == freeze:
                out.frozen.append((str(symbol), int(rank)))
        return out
    finally:
        db.close()


def recorded(day: str, database: Path | None = None) -> bool:
    db = board_store.read_only(database)
    if db is None:
        return False
    try:
        return LEADERBOARD_SOURCE_RECORDED in day_sources(db, day)
    finally:
        db.close()


class MissingInput(LookupError):
    """A file the build needs to see every stock that can be on the list cannot be read: the build fails with
    the reason, never a list that quietly leaves those stocks out."""


def universe() -> set[str]:
    """Common stocks and ADRs in Massive's reference (``tickers.json``). Unreadable is ``MissingInput``: without it
    a stock the store never held that day cannot be checked."""
    path = massive_files.root() / "store" / "reference" / "tickers.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("not a list of tickers")
    except (OSError, ValueError) as exc:
        raise MissingInput(f"Massive's reference list of stocks ({path}) could not be read: {exc}") from exc
    return {str(r["ticker"]) for r in rows
            if isinstance(r, dict) and r.get("ticker") and r.get("type") in LEADERBOARD_SECONDS_UNIVERSE_TYPES}


def minute_bars(day: str, keep: Callable[[str], bool]) -> dict[str, list[Bar]]:
    """The day's minute bars of every ticker ``keep`` admits, sorted by start (the file is sorted by ticker)."""
    path = massive_files.day_file(SIM_MASSIVE_MINUTES, day)
    if path is None:
        raise FileNotFoundError(f"No Massive minute file for {day}")
    bars: dict[str, list[Bar]] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        col = {name: header.index(name) for name in ("ticker", "window_start", "high", "close", "volume")}
        t, w, h, c, v = (col[name] for name in ("ticker", "window_start", "high", "close", "volume"))
        for row in reader:
            ticker = row[t]
            if not keep(ticker):
                continue
            bars.setdefault(ticker, []).append((int(row[w]) // 1_000_000_000, float(row[h]), float(row[c]),
                                                float(row[v] or 0.0)))
    for series in bars.values():
        series.sort()
    return bars


def _prior_session(day: str) -> str | None:
    """The session before ``day``: the last earlier date with a minute file, as the rebuild takes it."""
    d = date_cls.fromisoformat(day)
    for back in range(1, _PRIOR_SESSION_LOOKBACK_DAYS + 1):
        prior = (d - timedelta(days=back)).isoformat()
        if massive_files.day_file(SIM_MASSIVE_MINUTES, prior) is not None:
            return prior
    return None


def splits() -> list[tuple[str, str, float, float]]:
    """Massive's split list plus the SEC-confirmed ones (Massive's entry wins a tie), as the rebuild reads them."""
    from chart_events.constants_chart_events import CHART_EVENTS_CONFIRMED_SPLITS_SCHEMA_VERSION
    from chart_events.split_sources import list_paths

    def confirmed_rows(raw) -> list:
        if not isinstance(raw, dict) or raw.get("schema_version") != CHART_EVENTS_CONFIRMED_SPLITS_SCHEMA_VERSION:
            raise ValueError(f"schema_version is not {CHART_EVENTS_CONFIRMED_SPLITS_SCHEMA_VERSION}")
        return list(raw.get("splits") or [])

    def massive_rows(raw) -> list:
        if not isinstance(raw, list):
            raise ValueError("not a list of splits")
        return raw

    massive_path, confirmed_path = list_paths()
    out: dict[tuple[str, str], tuple[str, str, float, float]] = {}
    # No SEC-confirmed file means none confirmed; Massive's own list must be there.
    for path, parse, wins in ((confirmed_path, confirmed_rows, False), (massive_path, massive_rows, True)):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows = parse(raw)
        except FileNotFoundError as exc:
            if path == confirmed_path:
                continue
            raise MissingInput(f"Massive's split list ({path}) is not on disk") from exc
        except (OSError, ValueError) as exc:
            raise MissingInput(f"The split list {path} could not be read: {exc}") from exc
        for r in rows:
            try:
                item = (str(r["ticker"]), str(r["execution_date"]), float(r["split_from"]), float(r["split_to"]))
            except (KeyError, TypeError, ValueError):
                continue
            if item[2] > 0 and item[3] > 0 and (wins or item[:2] not in out):
                out[item[:2]] = item
    return list(out.values())


def outside_prior_closes(day: str, symbols: list[str]) -> dict[str, float]:
    """The prior close of stocks the store never held that day: the session before's day bar, split-adjusted
    as the rebuild adjusts it (a split executing after that session and by ``day``)."""
    if not symbols:
        return {}
    prior = _prior_session(day)
    if prior is None or massive_files.day_file(SIM_MASSIVE_DAYS, prior) is None:
        raise MissingInput(f"The Massive day bars of the session before {day} are not on disk")
    closes = massive_daily.closes(prior)
    wanted = set(symbols)
    factor = {s: 1.0 for s in wanted}
    for ticker, executed, split_from, split_to in splits():
        if ticker in wanted and prior < executed <= day:
            factor[ticker] *= split_from / split_to
    return {s: closes[s] * factor[s] for s in wanted if s in closes}


class Cancelled(Exception):
    """The build was asked to stop."""


def _build_index(path: Path, root: Path, stop: threading.Event | None, waiting: Callable[[], None] | None) -> bool:
    """``massive_index.build`` on a helper thread, ``waiting`` called every poll meanwhile (the job's heartbeat:
    a whole day file takes minutes); True when it saved the index. A build another process holds returns at once."""
    done: list = []
    failed: list[BaseException] = []

    def build() -> None:
        try:
            done.append(massive_index.build(path, root, stop))
        except BaseException as exc:  # noqa: BLE001 -- raised again on the build's own thread below
            failed.append(exc)

    worker = threading.Thread(target=build, daemon=True, name="board-seconds-index")
    worker.start()
    while worker.is_alive():
        worker.join(LEADERBOARD_SECONDS_INDEX_POLL_SEC)
        if worker.is_alive() and waiting is not None:
            waiting()
    if failed:
        raise failed[0]
    if stop is not None and stop.is_set():
        raise Cancelled()
    return bool(done and done[0] is not None)


def ensure_index(day: str, stop: threading.Event | None, waiting: Callable[[], None] | None = None) -> str:
    """Make sure the day's trades file can be entered at a ticker: ``indexed`` (it was), ``built`` (now),
    ``waited`` (another build held it and finished) or ``streamed`` (no index: every ticker is read from the start)."""
    path = massive_files.day_file(SIM_MASSIVE_TRADES, day)
    if path is None:
        raise FileNotFoundError(f"No Massive trades file for {day}")
    root = massive_files.root()
    if not massive_index.available():
        return "streamed"
    if massive_index.is_current(path, root):
        return "indexed"
    if _build_index(path, root, stop, waiting):
        return "built"
    deadline = time.monotonic() + LEADERBOARD_SECONDS_INDEX_WAIT_SEC
    while time.monotonic() < deadline:
        if stop is not None and stop.is_set():
            raise Cancelled()
        if massive_index.is_current(path, root):
            return "waited"
        if waiting is not None:
            waiting()
        time.sleep(LEADERBOARD_SECONDS_INDEX_POLL_SEC)
        if not massive_index.is_current(path, root) and _build_index(path, root, stop, waiting):
            return "built"                          # the other build ended without saving one
    logger.warning("Gappers by the second: no index for %s after %d s; reading it from the start", path,
                   LEADERBOARD_SECONDS_INDEX_WAIT_SEC)
    return "streamed"


class TradeRead:
    """One stock's prints on the day, up to ``until`` (epoch s): ``(ns, sequence, price, size, sets_price)``.

    Cancels and errors are left out (``SIM_MASSIVE_DROPPED_CORRECTIONS``), and so are the official open / close and
    corrected-close records (``massive_files.repeats_a_print``): they repeat an auction print, which counted the
    opening and closing cross twice in the boards' volume. A ticker's block is in SIP time and
    sequence order, so the read stops at its first print at or after ``until``. ``indexed`` says whether the read
    entered the file through its index.
    """

    def __init__(self, day: str, symbol: str, until: int, stop: threading.Event | None = None):
        self.day, self.symbol, self.until_ns, self.stop = day, symbol, int(until) * 1_000_000_000, stop
        self.indexed = False

    def __iter__(self) -> Iterator[Print]:
        path = massive_files.day_file(SIM_MASSIVE_TRADES, self.day)
        if path is None:
            raise FileNotFoundError(f"No Massive trades file for {self.day}")
        with massive_files.DayRead(path, self.symbol) as read:
            try:
                for header, lines in read.batches(stop=self.stop):
                    col = {name: header.index(name) for name in
                           ("sip_timestamp", "sequence_number", "price", "size", "conditions", "correction")}
                    ts, seq, px, sz, cond, corr = (col[name] for name in
                                                    ("sip_timestamp", "sequence_number", "price", "size",
                                                     "conditions", "correction"))
                    for fields in csv.reader(line.decode("utf-8") for line in lines):
                        correction = int(float(fields[corr] or 0))
                        if correction in SIM_MASSIVE_DROPPED_CORRECTIONS or massive_files.repeats_a_print(fields[cond]):
                            continue
                        ns = int(fields[ts])
                        if ns >= self.until_ns:
                            return
                        yield (ns, int(float(fields[seq] or 0)), float(fields[px]), float(fields[sz] or 0.0),
                               massive_files.sets_price(fields[cond], correction))
            except massive_files.Cancelled as exc:
                raise Cancelled() from exc
            finally:
                self.indexed = read.indexed         # set on entering the file, whether or not it holds the ticker
