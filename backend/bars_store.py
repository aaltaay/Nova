"""Durable IBKR chart-bar store on archive.db (ADR 012).

Reads never touch the broker. One candle identity: ``(symbol, timeframe, ts)``.
``historical_service`` writes source=ibkr (authoritative). Scanner L1 writes
source=ibkr_l1 and may only insert or refine a live row -- never a hist row.
Live minutes must not stamp hist coverage -- a streamed tip is not a finished fill.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from archive import db as archive_db
from archive.capture import session_date_for_ts
from constants import (
    ARCHIVE_SOURCE_IBKR,
    ARCHIVE_SOURCE_IBKR_L1,
    IBKR_BARS_STORE_FRESH_DAILY_SEC,
    IBKR_BARS_STORE_FRESH_INTRADAY_SEC,
    IBKR_BARS_STORE_MIN_BARS,
)
from ibkr.historical_derive import bar_unix, unix_to_iso

_HIST_UPSERT_SQL = """
INSERT INTO bars_intraday
    (symbol, timeframe, ts, open, high, low, close, volume, source, session_date)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(symbol, timeframe, ts) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume,
    source = excluded.source,
    session_date = excluded.session_date
"""

_LIVE_UPSERT_SQL = f"""
INSERT INTO bars_intraday
    (symbol, timeframe, ts, open, high, low, close, volume, source, session_date)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(symbol, timeframe, ts) DO UPDATE SET
    high = MAX(high, excluded.high),
    low = MIN(low, excluded.low),
    close = excluded.close,
    volume = CASE WHEN excluded.volume > 0 THEN excluded.volume ELSE volume END,
    session_date = excluded.session_date
WHERE source = '{ARCHIVE_SOURCE_IBKR_L1}'
"""

logger = logging.getLogger(__name__)

_DAILY_TFS = frozenset({"1Day", "1Week", "1Month"})


def coverage_from_bars(
    bars: list[dict],
    *,
    filling: bool,
    derived_from: str | None = None,
) -> dict[str, Any]:
    last = None
    if bars:
        last = bars[-1].get("t")
    return {
        "as_of": last,
        "complete_through": last,
        "filling": bool(filling),
        "derived_from": derived_from,
    }


def _fresh_ttl(timeframe: str) -> float:
    if timeframe in _DAILY_TFS:
        return float(IBKR_BARS_STORE_FRESH_DAILY_SEC)
    return float(IBKR_BARS_STORE_FRESH_INTRADAY_SEC)


def is_coverage_fresh(coverage: dict[str, Any] | None, timeframe: str) -> bool:
    if not coverage:
        return False
    fetched = coverage.get("fetched_ts")
    if fetched is None:
        return False
    return (time.time() - float(fetched)) <= _fresh_ttl(timeframe)


def store_series_complete(timeframe: str, bar_count: int) -> bool:
    """A stub (tape leftover / 1 live tip / today-only derive) is not a fill."""
    if bar_count <= 0:
        return False
    if timeframe in _DAILY_TFS:
        return True
    return bar_count >= int(IBKR_BARS_STORE_MIN_BARS.get(timeframe, 24))


def write_payload(payload: dict[str, Any]) -> None:
    """Upsert hist bars + coverage. Always tags ``ibkr``; payload source is ignored.

    Errors must never call this.
    """
    symbol = str(payload.get("symbol") or "").upper()
    timeframe = str(payload.get("timeframe") or "")
    bars = payload.get("bars") or []
    if not symbol or not timeframe:
        return
    coverage = payload.get("coverage") or coverage_from_bars(bars, filling=False)
    conn = archive_db.get_connection()
    try:
        for bar in bars:
            ts = bar_unix(bar)
            if ts is None:
                continue
            try:
                open_ = float(bar["o"])
                high = float(bar["h"])
                low = float(bar["l"])
                close = float(bar["c"])
                volume = float(bar.get("v") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            conn.execute(
                _HIST_UPSERT_SQL,
                (
                    symbol, timeframe, float(ts), open_, high, low, close, volume,
                    ARCHIVE_SOURCE_IBKR, session_date_for_ts(ts),
                ),
            )
        _upsert_coverage_locked(conn, symbol, timeframe, coverage)
        conn.commit()
    finally:
        conn.close()


def write_live_batch(conn, rows: list[tuple]) -> None:
    """L1 overlay. Caller owns the connection/transaction (write-queue drain)."""
    if rows:
        conn.executemany(_LIVE_UPSERT_SQL, rows)


def _upsert_coverage_locked(
    conn, symbol: str, timeframe: str, coverage: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO bars_coverage
            (symbol, timeframe, as_of, complete_through, filling, derived_from, fetched_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, timeframe) DO UPDATE SET
            as_of = excluded.as_of,
            complete_through = excluded.complete_through,
            filling = excluded.filling,
            derived_from = excluded.derived_from,
            fetched_ts = excluded.fetched_ts
        """,
        (
            symbol,
            timeframe,
            coverage.get("as_of"),
            coverage.get("complete_through"),
            1 if coverage.get("filling") else 0,
            coverage.get("derived_from"),
            float(coverage.get("fetched_ts") or time.time()),
        ),
    )


def read(symbol: str, timeframe: str, limit: int, *,
         through_ts: float | None = None) -> dict[str, Any] | None:
    """Return stored bars + coverage, or None on a total miss."""
    symbol = symbol.upper()
    limit = max(1, int(limit))
    conn = archive_db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT ts, open, high, low, close, volume, source
            FROM bars_intraday
            WHERE symbol = ? AND timeframe = ? AND (? IS NULL OR ts <= ?)
            ORDER BY ts DESC
            LIMIT ?
            """,
            (symbol, timeframe, through_ts, through_ts, limit),
        ).fetchall()
        # Chart store is bars_intraday only. Tape archive bars_1m / bars_1d is a
        # different product (often 1 print-built bar) and must not satisfy a miss.
        if not rows:
            return None
        rows = list(reversed(rows))
        bars = []
        for row in rows:
            bars.append({
                "t": unix_to_iso(float(row["ts"])),
                "o": float(row["open"]),
                "h": float(row["high"]),
                "l": float(row["low"]),
                "c": float(row["close"]),
                "v": int(row["volume"] or 0),
            })
        cov_row = conn.execute(
            """
            SELECT as_of, complete_through, filling, derived_from, fetched_ts
            FROM bars_coverage
            WHERE symbol = ? AND timeframe = ?
            """,
            (symbol, timeframe),
        ).fetchone()
        if cov_row:
            coverage = {
                "as_of": cov_row["as_of"],
                "complete_through": cov_row["complete_through"],
                "filling": bool(cov_row["filling"]),
                "derived_from": cov_row["derived_from"],
                "fetched_ts": float(cov_row["fetched_ts"]),
            }
        else:
            coverage = coverage_from_bars(bars, filling=True)
            coverage["fetched_ts"] = 0.0
        coverage["fresh"] = is_coverage_fresh(coverage, timeframe)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "source": ARCHIVE_SOURCE_IBKR,
            "cache": "store",
            "coverage": coverage,
        }
    except Exception:
        logger.exception("bars_store.read failed for %s %s", symbol, timeframe)
        return None
    finally:
        conn.close()


def empty_filling(symbol: str, timeframe: str) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "bars": [],
        "source": "ibkr",
        "cache": "miss",
        "coverage": coverage_from_bars([], filling=True),
    }
