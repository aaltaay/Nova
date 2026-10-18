"""News items and catalyst verdicts through the front door (ADR 059 / ADR 024), from the research catalyst store.

``<NOVA_CATALYST_DIR>/catalysts.sqlite3`` (default ``F:\\Nova\\catalysts``; schema ``research/catalysts/store.py``,
``PRAGMA user_version`` 1, any other refuses). Read-only; never the network.

  items     every article / filing fetched for the backfill: ``alpaca`` (the Benzinga newsroom), ``edgar`` (SEC
            filings, the 8-K's press release with them), ``finnhub`` (its free year: 2025 on), ``massive`` (Massive's
            archive -- nearly empty before 2021-04: its months up to 2021-03 are ~20 KB each). Kept only for the
            tickers the backfill targets and the months their windows touch: a ticker it never targeted has no items
            even on a day it made news. Finnhub's Benzinga copies are left out exactly as every research reader leaves
            them out (``store.HONEST_CLOCK_SQL``: their clock is four hours early, #516).
  verdicts  the live desk's own classifier (``backend/catalysts/classify.py``) per target symbol-day and rules
            version: catalyst (strong / weak), negative, routine_only, noise_only, none_found. The targets are the
            Five Pillars gap universe without its news pillar (2021-10-11 .. 2026-09-21, cutoff 09:30 ET) and the
            rebuilt whole-market board's top-10 movers at $1-$20 with 100k+ shares (2026-06-17 .. 2026-09-21, cutoff
            the first top-10 minute; a symbol-day in both keeps the earlier cutoff). ``cutoff_kind`` ``target`` (the
            only one stored) is that per-target cutoff.

As-of rule: a window opens at the prior session's 16:00 ET close; an item counts only if published at or before the
cutoff (``at`` here) -- never later. ``none_found`` means the sources that answered looked and found nothing; a
symbol-day with no verdict was never judged: UNKNOWN, never "no news".
"""
from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO, roots

from constants_catalysts import CATALYST_RULES_VERSION


def _research_store():
    """``research/catalysts/store.py`` under its own module name, so its rule is read, never forked."""
    folder = REPO / "research" / "catalysts"
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))              # store.py imports cat_config from beside it
    name = "market_reads_catalyst_store"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, folder / "store.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


_STORE = _research_store()
HONEST_CLOCK_SQL = _STORE.HONEST_CLOCK_SQL
SCHEMA_VERSION = _STORE.SCHEMA_VERSION
ET = ZoneInfo("America/New_York")
DB_FILENAME = "catalysts.sqlite3"
DEFAULT_CUTOFF_KIND = "target"        # build_verdicts.py's only kind: each target's own cutoff
SOURCES = ("alpaca", "edgar", "finnhub", "massive")
RULE = ("an item counts from its published_ts; a verdict judges items published after the prior session's 16:00 ET "
        "close and at or before the target's cutoff; times ET")
COVERAGE = ("items: only tickers the backfill targeted, in the months their windows touch; Massive's archive nearly "
            "empty before 2021-04; Finnhub 2025 on; Finnhub Benzinga copies excluded (#516). verdicts: 2021-10-11.."
            "2026-09-21, Five Pillars gap universe (cutoff 09:30 ET) and 2026-06-17..2026-09-21 leaderboard top-10 "
            "movers $1-$20 (cutoff the first top-10 minute). A missing verdict is UNKNOWN, never 'no news'.")
ITEM_COLUMNS = ["item_id", "source", "publisher", "published_ts", "published_et", "title", "url", "form", "sec_items",
                "n_tickers"]
VERDICT_COLUMNS = ["symbol", "session_date", "cutoff_kind", "rules_version", "verdict", "category", "strength",
                   "title", "source", "published_et", "published_ts", "item_id", "sources_checked", "n_items",
                   "origin", "window_start_et", "cutoff_et"]
PAIR_KEYS = ("verdict", "category", "strength", "title", "source", "published_ts", "rules_version", "cutoff_kind",
             "cutoff_et", "origin")
_PARAM_CHUNK = 900


def db_path() -> Path:
    return Path(os.environ.get("NOVA_CATALYST_DIR") or roots.CATALYST_DEFAULT) / DB_FILENAME


def _connect() -> sqlite3.Connection:
    path = db_path()
    if not path.is_file():
        raise LookupError(f"{path} is not on disk (the research catalyst store; NOVA_CATALYST_DIR moves it)")
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION:
        db.close()
        raise RuntimeError(f"{path}: schema version {version} is not {SCHEMA_VERSION}; refusing to read")
    return db


def _et(ts: float | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str | None:
    return None if ts is None or pd.isna(ts) else datetime.fromtimestamp(float(ts), ET).strftime(fmt)


def _day_ts(day: str, plus_days: int = 0) -> float:
    return datetime.combine(date.fromisoformat(day) + timedelta(days=plus_days), datetime.min.time(), ET).timestamp()


def at_ts(at: str) -> float:
    """``'YYYY-MM-DD HH:MM'`` (or ``...:SS``) read as ET, as epoch seconds."""
    return datetime.fromisoformat(at.strip().replace("T", " ")).replace(tzinfo=ET).timestamp()


def _version_number(version: str) -> int:
    found = re.search(r"-v(\d+)-", version or "")
    return int(found.group(1)) if found else -1


def items(symbol: str, date_from: str | None = None, date_to: str | None = None, at: str | None = None,
          sources: list[str] | None = None, limit: int | None = None) -> pd.DataFrame:
    """Items naming ``symbol`` published from ``date_from`` 00:00 ET through ``date_to`` 23:59:59 ET and never after
    ``at`` (an ET cutoff: no look-ahead), oldest first; ``limit`` keeps the newest N. ``attrs['checks']``: which
    sources looked at each target symbol-day in the range (``ok`` with its count, ``out_of_range``, ...)."""
    symbol = symbol.strip().upper()
    where, args = ["t.ticker = ?", HONEST_CLOCK_SQL], [symbol]
    if date_from:
        where, args = [*where, "t.published_ts >= ?"], [*args, _day_ts(date_from)]
    if date_to:
        where, args = [*where, "t.published_ts < ?"], [*args, _day_ts(date_to, 1)]
    if at:
        where, args = [*where, "t.published_ts <= ?"], [*args, at_ts(at)]
    if sources:
        unknown = sorted(set(sources) - set(SOURCES))
        if unknown:
            raise ValueError(f"sources {unknown}: the store holds {', '.join(SOURCES)}")
        where, args = [*where, f"i.source IN ({', '.join('?' * len(sources))})"], [*args, *sources]
    joined = "FROM item_tickers t JOIN items i USING (item_id) WHERE "
    sql = ("SELECT i.item_id, i.source, i.publisher, i.published_ts, i.title, i.url, i.form, i.sec_items, i.n_tickers "
           f"{joined}{' AND '.join(where)} ORDER BY i.published_ts DESC, i.item_id")
    hidden = " AND ".join([w for w in where if w != HONEST_CLOCK_SQL] + [f"NOT ({HONEST_CLOCK_SQL})"])
    with closing(_connect()) as db:
        rows = db.execute(sql + (" LIMIT ?" if limit else ""), [*args, *([int(limit)] if limit else [])]).fetchall()
        excluded = db.execute(f"SELECT count(*) {joined}{hidden}", args).fetchone()[0]
        checks = _checks(db, symbol, date_from, date_to)
    cols = [c for c in ITEM_COLUMNS if c != "published_et"]
    frame = pd.DataFrame([dict(zip(cols, r, strict=True)) for r in reversed(rows)], columns=cols)
    frame.insert(4, "published_et", [_et(t) for t in frame["published_ts"]])
    frame.attrs.update(symbol=symbol, date_from=date_from, date_to=date_to, at=at, rule=RULE, coverage=COVERAGE,
                       units="published_ts epoch seconds; published_et ET", source=str(db_path()),
                       excluded_finnhub_benzinga=int(excluded), checks=checks)
    return frame


def _checks(db: sqlite3.Connection, symbol: str, date_from: str | None, date_to: str | None) -> list[dict]:
    sql, args = "SELECT session_date, source, status, n_items FROM checks WHERE ticker = ?", [symbol]
    if date_from:
        sql, args = sql + " AND session_date >= ?", [*args, date_from]
    if date_to:
        sql, args = sql + " AND session_date <= ?", [*args, date_to]
    cols = ("session_date", "source", "status", "n_items")
    return [dict(zip(cols, r, strict=True)) for r in db.execute(sql + " ORDER BY session_date, source", args)]


def _verdict_rows(db: sqlite3.Connection, where: list[str], args: list[Any]) -> list[dict[str, Any]]:
    cols = ("symbol", "session_date", "cutoff_kind", "rules_version", "verdict", "category", "strength", "title",
            "source", "published_ts", "item_id", "sources_checked", "n_items", "origin", "window_start", "cutoff")
    sql = ("SELECT v.ticker, v.session_date, v.cutoff_kind, v.rules_version, v.verdict, v.category, v.strength,"
           " v.title, v.source, v.published_ts, v.item_id, v.sources_checked, v.n_items, t.origin, t.window_start,"
           " t.cutoff FROM verdicts v LEFT JOIN targets t ON t.ticker = v.ticker AND t.session_date = v.session_date"
           f" WHERE {' AND '.join(where) or '1=1'}")
    return [dict(zip(cols, r, strict=True)) for r in db.execute(sql, args)]


def _newest(rows: list[dict[str, Any]], rules_version: str | None) -> list[dict[str, Any]]:
    if rules_version == "all":
        return rows
    if rules_version:
        return [r for r in rows if r["rules_version"] == rules_version]
    best: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        key = (r["symbol"], r["session_date"], r["cutoff_kind"])
        if key not in best or _version_number(r["rules_version"]) > _version_number(best[key]["rules_version"]):
            best[key] = r
    return list(best.values())


def _shaped(r: dict[str, Any]) -> dict[str, Any]:
    return {**r, "published_et": _et(r["published_ts"]), "window_start_et": _et(r.pop("window_start")),
            "cutoff_et": _et(r.pop("cutoff"))}


def verdicts(symbol: str | None = None, day: str | None = None, date_from: str | None = None,
             date_to: str | None = None, cutoff_kind: str | None = None,
             rules_version: str | None = None) -> pd.DataFrame:
    """Catalyst verdicts by symbol and session day: the newest rules version per (symbol, day, cutoff_kind) unless
    ``rules_version`` names one (``'all'``: every version). ``cutoff_et`` is the moment each was judged at."""
    if day and (date_from or date_to):
        raise ValueError("pass day= or date_from= / date_to=, not both")
    where, args = [], []
    for clause, value in (("v.ticker = ?", symbol and symbol.strip().upper()), ("v.session_date >= ?", day or date_from),
                          ("v.session_date <= ?", day or date_to), ("v.cutoff_kind = ?", cutoff_kind)):
        if value:
            where, args = [*where, clause], [*args, value]
    with closing(_connect()) as db:
        rows = [_shaped(r) for r in _newest(_verdict_rows(db, where, args), rules_version)]
    frame = pd.DataFrame(rows, columns=VERDICT_COLUMNS)
    if len(frame):
        frame = frame.sort_values(["session_date", "symbol", "cutoff_kind", "rules_version"]).reset_index(drop=True)
    stored = sorted(set(frame["rules_version"]), key=_version_number) if len(frame) else []
    frame.attrs.update(rule=RULE, coverage=COVERAGE, source=str(db_path()), units="published_ts epoch seconds; *_et ET",
                       classifier_rules_version=CATALYST_RULES_VERSION, rules_versions_read=stored,
                       warning=None if not stored or stored[-1] == CATALYST_RULES_VERSION else
                       f"stored verdicts are {stored[-1]}; the live classifier is {CATALYST_RULES_VERSION}")
    return frame


def for_pairs(pairs: list[tuple[str, str]], cutoff_kind: str = DEFAULT_CUTOFF_KIND
              ) -> dict[tuple[str, str], dict[str, Any] | None]:
    """``(day, symbol)`` -> the newest-rules verdict at ``cutoff_kind`` (``PAIR_KEYS``), for many stock-days in
    chunked reads. Every pair asked is a key; None means no verdict exists: UNKNOWN, never "no news"."""
    by_day: dict[str, set[str]] = defaultdict(set)
    for day, symbol in pairs:
        by_day[str(day)[:10]].add(str(symbol).strip().upper())
    out: dict[tuple[str, str], dict[str, Any] | None] = {(d, s): None for d, ss in by_day.items() for s in ss}
    rows: list[dict[str, Any]] = []
    with closing(_connect()) as db:
        days, symbols = [], set()
        for d in [*sorted(by_day), None]:
            if days and (d is None or len(days) + len(symbols | by_day[d]) + 1 > _PARAM_CHUNK):
                rows += _verdict_rows(db, ["v.cutoff_kind = ?", f"v.session_date IN ({', '.join('?' * len(days))})",
                                           f"v.ticker IN ({', '.join('?' * len(symbols))})"],
                                      [cutoff_kind, *days, *sorted(symbols)])
                days, symbols = [], set()
            if d is not None:
                days.append(d)
                symbols |= by_day[d]
    for r in _newest([r for r in rows if (r["session_date"], r["symbol"]) in out], None):
        r = _shaped(r)
        out[(r["session_date"], r["symbol"])] = {k: r[k] for k in PAIR_KEYS}
    return out
