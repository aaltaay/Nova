"""Massive's reference dump through the front door (ADR 059): financial statements, float, IPOs, ticker details and
FINRA short interest, each answered for one stock and, where the data allows, as known on a past day.

The dump (``<NOVA_MARKET_DATA_DIR>/store/reference``) is about 1 GB of monthly JSON lines, filed by month: one
stock's balance sheets are spread over 130 files. A read goes through an index instead:

``<NOVA_MARKET_DATA_DIR>/store/reference_index.sqlite3`` -- owner: this module (the only writer and reader).
Invalidation: a dataset is rebuilt when any of its source files changes size or modified time (``sources`` table),
so a new dump is picked up by the next read. ``PRAGMA user_version`` = ``SCHEMA_VERSION``; another version refuses
loudly (``UnknownIndexVersion``), never read as found. Rows are the dump's records unchanged (JSON), keyed by
ticker, CIK and the dataset's date. A build takes one heavy-read slot (``slots.py``).

As-of rules (the point of a front door: no look-ahead):
  financials      a statement counts from its ``filing_date`` (Massive's), so ``as_of`` keeps filings on or before it.
  short interest  a FINRA settlement counts from ``backend/move_reason/short_interest.counts_from`` (its publish lag).
  float           Massive serves the latest float only (no history): it is labelled ``latest_only``, never as-of.
  ticker details  the dump's current values (``share_class_shares_outstanding`` included): ``latest_only``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO, roots, slots  # noqa: F401  (REPO puts backend/ on sys.path)

SCHEMA_VERSION = 1
INDEX_FILENAME = "reference_index.sqlite3"
FINANCIALS = ("balance_sheets", "income_statements", "cash_flow_statements")
MONTHLY = (*FINANCIALS, "ipos")
SINGLE_FILE = {"float": "float.jsonl", "ticker_details": "ticker_details.jsonl"}
DATASETS = (*MONTHLY, *SINGLE_FILE)
DATE_FIELD = {**{d: "filing_date" for d in FINANCIALS}, "ipos": "listing_date", "float": "effective_date",
              "ticker_details": None}
ET = ZoneInfo("America/New_York")

DDL = (
    "CREATE TABLE IF NOT EXISTS sources (dataset TEXT NOT NULL, file TEXT NOT NULL, size INTEGER NOT NULL,"
    " mtime_ns INTEGER NOT NULL, PRIMARY KEY (dataset, file))",
    "CREATE TABLE IF NOT EXISTS rows (dataset TEXT NOT NULL, ticker TEXT, cik TEXT, day TEXT, data TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS rows_by_ticker ON rows (dataset, ticker, day)",
    "CREATE INDEX IF NOT EXISTS rows_by_cik ON rows (dataset, cik, day)",
)


class UnknownIndexVersion(RuntimeError):
    """The index was written by another version of this module: never read or rebuilt as found."""


def index_path() -> Path:
    return roots.massive() / "store" / INDEX_FILENAME


def _source_files(dataset: str) -> list[Path]:
    ref = roots.reference()
    if dataset in SINGLE_FILE:
        path = ref / SINGLE_FILE[dataset]
        return [path] if path.is_file() else []
    folder = ref / dataset
    return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []


def _manifest(dataset: str) -> dict[str, tuple[int, int]]:
    out = {}
    for path in _source_files(dataset):
        st = path.stat()
        out[path.name] = (st.st_size, st.st_mtime_ns)
    return out


def _connect() -> sqlite3.Connection:
    path = index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=120.0)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, SCHEMA_VERSION):
        db.close()
        raise UnknownIndexVersion(f"{path} is schema version {version}, this reader knows {SCHEMA_VERSION}; "
                                  "move the file aside and the next read rebuilds it")
    if version == 0:
        db.execute("PRAGMA journal_mode=WAL")
        with db:
            for statement in DDL:
                db.execute(statement)
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return db


def _indexed(db: sqlite3.Connection, dataset: str) -> dict[str, tuple[int, int]]:
    rows = db.execute("SELECT file, size, mtime_ns FROM sources WHERE dataset = ?", (dataset,)).fetchall()
    return {f: (s, m) for f, s, m in rows}


def _cik(value: Any) -> str | None:
    text = str(value or "").strip().lstrip("0")
    return text or None


def _records(dataset: str, path: Path):
    """``(ticker, cik, day, json)`` per record; a financial statement names every ticker the company had."""
    field = DATE_FIELD[dataset]
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            day = str(rec.get(field) or "")[:10] or None if field else None
            data = json.dumps(rec, separators=(",", ":"))
            tickers = rec.get("tickers") if dataset in FINANCIALS else [rec.get("ticker")]
            tickers = [str(t).strip().upper() for t in tickers or [] if t] or [None]
            if tickers == [None] and dataset not in FINANCIALS:
                continue
            for ticker in tickers:
                yield ticker, _cik(rec.get("cik")), day, data


def ensure(dataset: str) -> dict[str, Any]:
    """Build or refresh ``dataset``'s rows when its source files changed; ``{dataset, rebuilt, rows, files}``."""
    if dataset not in DATASETS:
        raise ValueError(f"unknown reference dataset {dataset!r}; one of {', '.join(DATASETS)}")
    want = _manifest(dataset)
    if not want:
        raise LookupError(f"no {dataset} files under {roots.reference()}")
    db = _connect()
    try:
        if _indexed(db, dataset) == want:
            return {"dataset": dataset, "rebuilt": False, "files": len(want)}
        with slots.heavy(f"reference index {dataset}"):
            db.execute("BEGIN IMMEDIATE")
            try:
                if _indexed(db, dataset) == want:     # another process built it while this one waited
                    db.rollback()
                    return {"dataset": dataset, "rebuilt": False, "files": len(want)}
                db.execute("DELETE FROM rows WHERE dataset = ?", (dataset,))
                db.execute("DELETE FROM sources WHERE dataset = ?", (dataset,))
                n = 0
                for path in _source_files(dataset):
                    batch = [(dataset, *r) for r in _records(dataset, path)]
                    db.executemany("INSERT INTO rows VALUES (?, ?, ?, ?, ?)", batch)
                    n += len(batch)
                db.executemany("INSERT INTO sources VALUES (?, ?, ?, ?)",
                               [(dataset, f, s, m) for f, (s, m) in want.items()])
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return {"dataset": dataset, "rebuilt": True, "rows": n, "files": len(want)}
    finally:
        db.close()


def _frame(dataset: str, symbol: str | None, as_of: str | None = None, date_from: str | None = None,
           cik: str | None = None) -> pd.DataFrame:
    ensure(dataset)
    where, args = ["dataset = ?"], [dataset]
    if symbol:
        where.append("ticker = ?")
        args.append(symbol.strip().upper())
    if cik:
        where.append("cik = ?")
        args.append(_cik(cik))
    if as_of:
        where.append("day <= ?")
        args.append(as_of)
    if date_from:
        where.append("day >= ?")
        args.append(date_from)
    db = _connect()
    try:
        rows = db.execute(f"SELECT data FROM rows WHERE {' AND '.join(where)}", args).fetchall()
    finally:
        db.close()
    return pd.DataFrame([json.loads(r[0]) for r in rows])


def financials(symbol: str, statement: str = "balance_sheets", as_of: str | None = None,
               timeframe: str | None = None, cik: str | None = None) -> pd.DataFrame:
    """``symbol``'s statements as filed, oldest period first: only filings on or before ``as_of`` when given.

    ``statement`` is ``balance_sheets`` (dollar amounts: ``common_stock`` and ``treasury_stock`` are dollars, not
    shares), ``income_statements`` (``basic_shares_outstanding`` / ``diluted_shares_outstanding`` are the period's
    share counts behind EPS) or ``cash_flow_statements``. ``timeframe``: ``quarterly`` / ``annual`` / ... A symbol
    the statements do not name is looked up by its SEC CIK (``attrs['matched']`` says which). A ticker two companies
    used (``tickers.py``) keeps only the statements of the company that held it on ``as_of`` (today without one;
    ``cik`` overrides), by the statements' own ``cik``; a day that cannot be settled refuses with the candidates."""
    from market_reads import tickers
    if statement not in FINANCIALS:
        raise ValueError(f"statement must be one of {', '.join(FINANCIALS)}")
    held = tickers.resolve(symbol, as_of, cik)
    if held["ticker_reused"] or cik:
        held = tickers.require(symbol, as_of, cik)
    frame, matched = _frame(statement, symbol, as_of), "ticker"
    if not frame.empty and held["cik"] and (held["ticker_reused"] or cik) and "cik" in frame:
        frame, matched = frame[frame["cik"].map(_cik) == held["cik"]], f"ticker, cik {held['cik']}"
    if frame.empty and held["cik"]:
        frame, matched = _frame(statement, None, as_of, cik=held["cik"]), f"cik {held['cik']}"
    if not frame.empty:
        if timeframe:
            frame = frame[frame["timeframe"] == timeframe]
        frame = frame.sort_values(["period_end", "filing_date"]).reset_index(drop=True)
    frame.attrs.update(dataset=statement, symbol=symbol.upper(), as_of=as_of or "latest", matched=matched,
                       rule="a statement counts from its filing_date", ticker=tickers.summary(held))
    return frame


def float_latest(symbol: str | None = None) -> pd.DataFrame:
    """Massive's free float (insiders, 5%+ holders, locked-up and restricted shares excluded). Latest only:
    Massive keeps no history, so this is never a past day's float."""
    frame = _frame("float", symbol)
    frame.attrs.update(dataset="float", symbol=symbol.upper() if symbol else None, as_of="latest_only",
                       rule="Massive's latest free float; not point-in-time")
    return frame


def ipos(symbol: str | None = None, date_from: str | None = None, date_to: str | None = None) -> pd.DataFrame:
    """IPOs by listing date (Massive, 2008 on); no lockup terms (Massive does not carry them)."""
    frame = _frame("ipos", symbol, date_to, date_from)
    if not frame.empty and "listing_date" in frame:
        frame = frame.sort_values("listing_date").reset_index(drop=True)
    frame.attrs.update(dataset="ipos", symbol=symbol.upper() if symbol else None, date_from=date_from,
                       date_to=date_to)
    return frame


def ticker_details(symbol: str) -> pd.DataFrame:
    """The dump's ticker details (name, CIK, exchange, SIC, list date, share class shares outstanding): current
    values as of the dump, never a past day's."""
    frame = _frame("ticker_details", symbol)
    frame.attrs.update(dataset="ticker_details", symbol=symbol.upper(), as_of="latest_only",
                       rule="current values as of the reference dump")
    return frame


def short_interest(symbol: str, day: str, at: str = "09:30") -> dict[str, Any]:
    """FINRA short interest as published by ``day`` ``at`` ET: the newest settlement that counts by then
    (``backend/move_reason/short_interest.published_at``: ``{row, counts_from, pending}``)."""
    from move_reason import short_interest as finra
    d = date.fromisoformat(day)
    hh, mm = (int(x) for x in at.split(":"))
    moment = datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp()
    answer = finra.published_at(symbol.strip().upper(), moment)
    return {"symbol": symbol.upper(), "day": day, "at": at, **answer}
