"""The hot list's file (ADR 044): ``hot-list.json`` in the operator cache, plus a read-only copy per day.

Shape (schema 1): ``{schema_version, date, auto_n, default: {buy, sell}, entries: [{symbol, how, at,
board, rank, change_pct}], yesterday: [symbol]}``. ``date`` is the trading day, which starts at 04:00 ET
(the practice day's boundary); ``at`` is epoch seconds; ``change_pct`` is the leaderboard row's, a
fraction against the prior close (``null`` for a star). An unknown version or an unreadable file reads
as an empty list with the error stated; nothing guesses.

``save`` writes today's list and its day copy ``hot-list/YYYY-MM-DD.json``, so the triggers audit can
read any day (``entries_on``); the rollover writes the old day's final copy (``archive``). A day copy is
never written again once its day is over. Reads of today's file are cached by its size and modification
time: HOD Momo's active set asks on every rebuild.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Any

from constants_hot_list import (
    HOT_LIST_AUTO_N_CHOICES,
    HOT_LIST_AUTO_N_DEFAULT,
    HOT_LIST_BOARD_GAINERS,
    HOT_LIST_DATE_RE,
    HOT_LIST_DAY_DIR,
    HOT_LIST_DEFAULT_SIDE,
    HOT_LIST_FILE,
    HOT_LIST_HOW_STAR,
    HOT_LIST_HOWS,
    HOT_LIST_SCHEMA_VERSION,
    HOT_LIST_SIDES,
    HOT_LIST_SYMBOL_RE,
)

logger = logging.getLogger(__name__)

_SYMBOL = re.compile(HOT_LIST_SYMBOL_RE)
_DATE = re.compile(HOT_LIST_DATE_RE)
_cache_lock = threading.Lock()
# Today's file as last parsed: (path, (mtime_ns, size), document, error).
_cache: tuple[str, tuple[int, int], dict[str, Any] | None, str | None] | None = None


def _path() -> Path:
    from paths import cache_dir

    return cache_dir() / HOT_LIST_FILE


def is_date(day: Any) -> bool:
    """A real ``YYYY-MM-DD`` day (digits and dashes only: safe to put in a file name)."""
    if not isinstance(day, str) or not _DATE.match(day):
        return False
    try:
        date.fromisoformat(day)
    except ValueError:
        return False
    return True


def _day_path(day: str) -> Path:
    """The day copy of ``day``. Only a ``YYYY-MM-DD`` string is ever made into a path."""
    if not is_date(day):
        raise ValueError(f"not a day: {day!r}")
    from paths import cache_dir

    return cache_dir() / HOT_LIST_DAY_DIR / f"{day}.json"


def valid_symbol(raw: Any) -> str | None:
    """``raw`` as a listed ticker (upper case), or None when it is not one."""
    sym = str(raw or "").strip().upper()
    return sym if _SYMBOL.match(sym) else None


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


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if isfinite(float(value)) else None


def _entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    sym = valid_symbol(raw.get("symbol"))
    if sym is None:
        return None
    rank = raw.get("rank")
    return {"symbol": sym, "how": raw.get("how") if raw.get("how") in HOT_LIST_HOWS else HOT_LIST_HOW_STAR,
            "at": _num(raw.get("at")),
            "board": HOT_LIST_BOARD_GAINERS if raw.get("board") == HOT_LIST_BOARD_GAINERS else None,
            "rank": rank if isinstance(rank, int) and not isinstance(rank, bool) else None,
            "change_pct": _num(raw.get("change_pct"))}


def normalize(doc: dict[str, Any], name: str = HOT_LIST_FILE) -> dict[str, Any]:
    """Every field in its shape: an entry without a ticker (or a second one of a ticker) is dropped, an
    unknown ``auto_n`` or side reads as the default. Each change is logged, never silent."""
    out = empty(str(doc.get("date")))
    auto_n = doc.get("auto_n")
    known = isinstance(auto_n, int) and not isinstance(auto_n, bool) and auto_n in HOT_LIST_AUTO_N_CHOICES
    out["auto_n"] = auto_n if known else HOT_LIST_AUTO_N_DEFAULT
    default = doc.get("default") if isinstance(doc.get("default"), dict) else {}
    out["default"] = {side: default.get(side) if default.get(side) in HOT_LIST_SIDES else HOT_LIST_DEFAULT_SIDE
                      for side in ("buy", "sell")}
    raw_entries = doc.get("entries") if isinstance(doc.get("entries"), list) else []
    seen: set[str] = set()
    for raw in raw_entries:
        entry = _entry(raw)
        if entry is not None and entry["symbol"] not in seen:
            seen.add(entry["symbol"])
            out["entries"].append(entry)
    raw_yesterday = doc.get("yesterday") if isinstance(doc.get("yesterday"), list) else []
    out["yesterday"] = list(dict.fromkeys(s for s in (valid_symbol(r) for r in raw_yesterday) if s))
    if (len(out["entries"]) != len(raw_entries) or len(out["yesterday"]) != len(raw_yesterday)
            or out["auto_n"] != doc.get("auto_n") or out["default"] != doc.get("default")):
        logger.warning("hot list: %s held fields out of shape; they read as their defaults (entries %d -> %d)",
                       name, len(raw_entries), len(out["entries"]))
    return out


def roll(doc: dict[str, Any] | None, day: str) -> dict[str, Any]:
    """``day``'s fresh list after ``doc`` (an earlier day's): its names become ``yesterday`` -- or, when
    that day listed none, the names it carried, so a weekend between two sessions keeps Friday's -- and
    its settings stay. Pure."""
    out = empty(day)
    if doc is None:
        return out
    out["auto_n"] = doc.get("auto_n", out["auto_n"])
    out["default"] = dict(doc.get("default") or out["default"])
    names = [str(e["symbol"]) for e in doc.get("entries") or [] if e.get("symbol")]
    out["yesterday"] = names or list(doc.get("yesterday") or [])
    return out


def _parse(p: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("hot list: %s is unreadable", p, exc_info=True)
        return None, f"{p.name} is unreadable: {exc}"
    if not isinstance(doc, dict) or doc.get("schema_version") != HOT_LIST_SCHEMA_VERSION:
        version = doc.get("schema_version") if isinstance(doc, dict) else "?"
        logger.warning("hot list: %s has schema_version %s -- refused", p, version)
        return None, f"{p.name} has schema_version {version}; this build reads {HOT_LIST_SCHEMA_VERSION}"
    if not is_date(doc.get("date")):
        logger.warning("hot list: %s names no trading day (%r) -- refused", p, doc.get("date"))
        return None, f"{p.name} names no trading day (date {doc.get('date')!r})"
    return normalize(doc, p.name), None


def read_raw(path: Path | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """``(document, error)``: the file as it is, or why it cannot be read (``None, None`` when absent)."""
    global _cache
    p = path or _path()
    try:
        st = p.stat()
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        logger.warning("hot list: %s cannot be read", p, exc_info=True)
        return None, f"{p.name} is unreadable: {exc}"
    signature = (int(st.st_mtime_ns), int(st.st_size))
    if path is None:
        with _cache_lock:
            hit = _cache
        if hit is not None and hit[0] == str(p) and hit[1] == signature:
            return copy.deepcopy(hit[2]), hit[3]
    doc, error = _parse(p)
    if path is None:
        with _cache_lock:
            _cache = (str(p), signature, doc, error)
    return copy.deepcopy(doc), error


def write(doc: dict[str, Any], path: Path | None = None) -> None:
    """Through a temp file and a rename, so a crash never leaves half a file."""
    p = path or _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name, dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        os.replace(tmp, p)
        if path is None:
            _forget_cache()                  # never serve the old list under a coarse file clock
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:  # maintainer: allow-swallow the temp file may already be gone
            pass
        raise


def save(doc: dict[str, Any]) -> None:
    """Today's list, and its day copy. A copy that cannot be written is removed (the triggers audit then
    reads today's file) and logged; the list itself raises ``OSError`` when it cannot be written."""
    write(doc)
    try:
        write(doc, _day_path(doc["date"]))
    except (OSError, ValueError):
        logger.exception("hot list: the day copy of %s could not be written", doc.get("date"))
        try:
            _day_path(doc["date"]).unlink(missing_ok=True)
        except (OSError, ValueError):
            logger.exception("hot list: a stale day copy of %s may remain", doc.get("date"))


def archive(doc: dict[str, Any]) -> str | None:
    """The final copy of an earlier day's list (the rollover's). None, or why it was not written."""
    try:
        write(doc, _day_path(doc["date"]))
    except (OSError, ValueError) as exc:
        logger.exception("hot list: the day copy of %s could not be written at the rollover", doc.get("date"))
        return f"the day copy of {doc.get('date')} could not be written: {exc}"
    return None


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


def listed_or_unread(symbol: str, now: float | None = None) -> tuple[bool, str | None]:
    """Whether ``symbol`` is on today's list, and -- when the list cannot be read -- why, in words a page can
    show (the file's own error goes to the log, never to the desk). Unreadable lists nothing: not listed."""
    doc, error = current(now)
    if error is not None:
        logger.warning("hot list: today's list cannot be read -- %s counts as not listed: %s", symbol, error)
        return False, "today's hot list could not be read (the backend log has the error)"
    sym = (symbol or "").strip().upper()
    return sym in {str(e.get("symbol") or "").upper() for e in doc.get("entries") or []}, None


def entries_on(day: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """The list's entries for a past or present day (the day copy, else today's file), with any error."""
    if not is_date(day):
        return None, f"not a day: {day!r} (YYYY-MM-DD)"
    doc, error = read_raw(_day_path(day))
    if doc is None and error is None:
        live, live_error = read_raw()
        if live is not None and live.get("date") == day:
            return list(live.get("entries") or []), None
        return None, live_error or f"no hot list kept for {day}"
    if doc is None:
        return None, error
    return list(doc.get("entries") or []), None


def _forget_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def forget_cache_for_tests() -> None:
    _forget_cache()
