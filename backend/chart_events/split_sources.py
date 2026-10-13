"""The three split lists the daily charts' M marks merge (``splits.py``), read for one symbol.

  massive         the operator's Massive reference archive, ``<NOVA_MARKET_DATA_DIR>/store/reference/splits.json``
  sec_confirmed   the splits SEC filings proved that Massive's list misses, ``splits_confirmed.json`` beside the
                  leaderboard store (#772; an unknown ``schema_version`` is an error, never read)
  yahoo           Yahoo's split history, given up after ``CHART_EVENTS_YAHOO_TIMEOUT_SEC``

The two files are read again when they change. A list that is absent, unreadable or late is named in the
answer's ``lists``, never read as "no splits"; with none read, the last good events stand.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Callable

from chart_events import splits
from chart_events.constants_chart_events import (
    CHART_EVENTS_CONFIRMED_SPLITS_FILE,
    CHART_EVENTS_CONFIRMED_SPLITS_SCHEMA_VERSION,
    CHART_EVENTS_MASSIVE_SPLITS_FILE,
    CHART_EVENTS_YAHOO_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)
YahooSplits = Callable[[str], list]
ListPaths = Callable[[], tuple[Path, Path]]

# Two workers: a Yahoo call that hangs past its timeout still holds one.
_YAHOO_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chart_events_yahoo")


def _why(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:200]


def yahoo_splits(symbol: str) -> list:
    """Yahoo's split history as ``(when, ratio)`` rows; an empty list when Yahoo lists none."""
    import yfinance as yf

    table = yf.Ticker(symbol).splits
    # yfinance 1.x answers a one-column frame ("Stock Splits"); older releases answered a series.
    series = table.iloc[:, 0] if getattr(table, "ndim", 1) == 2 else table
    return [(when, float(ratio)) for when, ratio in series.items()]


def list_paths() -> tuple[Path, Path]:
    """Massive's reference split list and the SEC-confirmed splits beside the leaderboard store."""
    from leaderboard import store as leaderboard_store
    from sim import massive_files

    return (massive_files.root().joinpath(*CHART_EVENTS_MASSIVE_SPLITS_FILE),
            leaderboard_store.root() / CHART_EVENTS_CONFIRMED_SPLITS_FILE)


class _SplitList:
    """One split list file, by ticker, read again when the file changes."""

    def __init__(self, name: str, parse: Callable[[Any], list]):
        self.name, self._parse = name, parse
        self._key: tuple | None = None
        self._by_ticker: dict[str, list] = {}

    def rows(self, path: Path, symbol: str) -> tuple[list, dict[str, Any]]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return [], {"status": "absent", "path": str(path)}
        except OSError as exc:
            return [], {"status": "error", "path": str(path), "error": _why(exc)}
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key != self._key:
            try:
                rows = self._parse(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001 -- an unreadable list is said, never read as "no splits"
                logger.warning("chart events: %s split list %s unreadable: %s", self.name, path, exc)
                return [], {"status": "error", "path": str(path), "error": _why(exc)}
            by_ticker: dict[str, list] = {}
            for row in rows:
                by_ticker.setdefault(str(row.get("ticker") or "").upper(), []).append(row)
            self._key, self._by_ticker = key, by_ticker
        return self._by_ticker.get(symbol, []), {"status": "read", "path": str(path)}


def _massive_rows(raw: Any) -> list:
    if not isinstance(raw, list):
        raise ValueError("not a list of splits")
    return raw


def _confirmed_rows(raw: Any) -> list:
    version = raw.get("schema_version") if isinstance(raw, dict) else None
    if version != CHART_EVENTS_CONFIRMED_SPLITS_SCHEMA_VERSION:
        raise ValueError(f"schema_version {version!r} is not {CHART_EVENTS_CONFIRMED_SPLITS_SCHEMA_VERSION}")
    return list(raw.get("splits") or [])


class SplitSources:
    """The three lists, read for one symbol at a time on the reader's thread."""

    def __init__(self, *, yahoo: YahooSplits = yahoo_splits, paths: ListPaths = list_paths):
        self._yahoo, self._paths = yahoo, paths
        self._massive = _SplitList("Massive", _massive_rows)
        self._confirmed = _SplitList("SEC-confirmed", _confirmed_rows)

    def read(self, sym: str, since: date, held: dict[str, Any]) -> dict[str, Any]:
        massive_path, confirmed_path = self._paths()
        massive, massive_state = self._massive.rows(massive_path, sym)
        confirmed, confirmed_state = self._confirmed.rows(confirmed_path, sym)
        try:
            yahoo = _YAHOO_POOL.submit(self._yahoo, sym).result(timeout=CHART_EVENTS_YAHOO_TIMEOUT_SEC)
            yahoo_state: dict[str, Any] = {"status": "read"}
        except Exception as exc:  # noqa: BLE001 -- a timeout or a Yahoo error is said, never read as "no splits"
            logger.warning("chart events: Yahoo split read failed for %s: %s", sym, exc)
            yahoo, yahoo_state = [], {"status": "error", "error": _why(exc)}
        states = {"massive": massive_state, "sec_confirmed": confirmed_state, "yahoo": yahoo_state}
        errors = [f"{k}: {v['error']}" for k, v in states.items() if v["status"] == "error"]
        read_any = any(v["status"] == "read" for v in states.values())
        events = splits.events(massive=massive, confirmed=confirmed, yahoo=yahoo, since=since)
        if not read_any:
            events = (held.get("splits") or {}).get("events") or []
        return {"status": "read" if read_any else "error", "lists": states, "error": "; ".join(errors) or None,
                "events": events}
