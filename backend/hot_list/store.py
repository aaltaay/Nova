"""The hot list's file (ADR 043): ``hot-list.json`` in the operator cache, plus a read-only copy per day.

Shape (schema 1): ``{schema_version, date, auto_n, default: {buy, sell}, entries: [{symbol, how, at,
board, rank, change_pct}], yesterday: [symbol]}``. ``date`` is the trading day, which starts at 04:00 ET
(the practice day's boundary). An unknown version or an unreadable file reads as an empty list with
the error stated; nothing guesses.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from constants_hot_list import (
    HOT_LIST_AUTO_N_DEFAULT,
    HOT_LIST_DAY_DIR,
    HOT_LIST_DEFAULT_SIDE,
    HOT_LIST_FILE,
    HOT_LIST_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


def _path() -> Path:
    from paths import cache_dir

    return cache_dir() / HOT_LIST_FILE


def _day_path(day: str) -> Path:
    from paths import cache_dir

    return cache_dir() / HOT_LIST_DAY_DIR / f"{day}.json"


def trading_day(now: float | None = None) -> str:
    """The trading day ``now`` belongs to (it starts at 04:00 ET), ``YYYY-MM-DD``."""
    from practice.clock import at, day_start_ts

    ts = time.time() if now is None else float(now)
    return at(day_start_ts(ts)).date().isoformat()


def empty(day: str) -> dict[str, Any]:
    return {
        "schema_version": HOT_LIST_SCHEMA_VERSION, "date": day, "auto_n": HOT_LIST_AUTO_N_DEFAULT,
        "default": {"buy": HOT_LIST_DEFAULT_SIDE, "sell": HOT_LIST_DEFAULT_SIDE}, "entries": [], "yesterday": [],
    }


def read_raw(path: Path | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """``(document, error)``: the file as it is, or why it cannot be read (``None, None`` when absent)."""
    p = path or _path()
    if not p.exists():
        return None, None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("hot list: %s is unreadable", p, exc_info=True)
        return None, f"{p.name} is unreadable: {exc}"
    if not isinstance(doc, dict) or doc.get("schema_version") != HOT_LIST_SCHEMA_VERSION:
        return None, f"{p.name} has schema_version {doc.get('schema_version') if isinstance(doc, dict) else '?'}; this build reads {HOT_LIST_SCHEMA_VERSION}"
    return doc, None


def write(doc: dict[str, Any], path: Path | None = None) -> None:
    """Through a temp file and a rename, so a crash never leaves half a file."""
    p = path or _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name, dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:  # maintainer: allow-swallow the temp file may already be gone
            pass
        raise


def current(now: float | None = None) -> tuple[dict[str, Any], str | None]:
    """Today's list (empty when the file belongs to an earlier day) and any read error."""
    day = trading_day(now)
    doc, error = read_raw()
    if doc is None or doc.get("date") != day:
        return empty(day), error
    return doc, None


def listed_symbols(now: float | None = None) -> list[str]:
    doc, _error = current(now)
    return [str(e.get("symbol") or "").upper() for e in doc.get("entries") or [] if e.get("symbol")]


def is_listed(symbol: str, now: float | None = None) -> bool:
    """Whether ``symbol`` is on today's list. An unreadable list lists nothing (Nova buys nothing)."""
    return (symbol or "").strip().upper() in set(listed_symbols(now))


def entries_on(day: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """The list's entries for a past or present day (the day copy, else today's file), with any error."""
    doc, error = read_raw(_day_path(day))
    if doc is None and error is None:
        live, live_error = read_raw()
        if live is not None and live.get("date") == day:
            return list(live.get("entries") or []), None
        return None, live_error or f"no hot list kept for {day}"
    if doc is None:
        return None, error
    return list(doc.get("entries") or []), None
