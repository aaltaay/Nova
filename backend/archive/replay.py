"""
Replay archived tape/bars through ``nova_os.decide`` (P9).

Loads a cold day (JSONL), builds per-symbol candidates + chart-shaped bars,
calls ``decide(..., record=False)``, and returns collected decisions.
Never places orders; never writes receipts.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from archive.compact import cold_root
from archive.manifest import read_manifest, verify_payload
from constants import (
    ARCHIVE_REPLAY_MAX_SYMBOLS,
    ARCHIVE_SCHEMA_VERSION,
    ARCHIVE_SOURCE_IBKR,
    NOVA_OS_DEFAULT_MODE,
)
from nova_os.decide import decide

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_table_rows(
    session_date: str,
    table: str,
    *,
    cold_dir: Path | None = None,
    schema_version: str = ARCHIVE_SCHEMA_VERSION,
) -> list[dict[str, Any]]:
    root = cold_dir or cold_root()
    day_dir = root / session_date / schema_version
    man_path = day_dir / f"{table}.manifest.json"
    if not man_path.is_file():
        return []
    man = read_manifest(man_path)
    payload = root / man["path"]
    if not verify_payload(payload, man["sha256"]):
        raise ValueError(f"sha256 mismatch for {table} on {session_date}")
    return _load_jsonl(payload)


def archive_bar_to_chart(row: dict[str, Any]) -> dict[str, Any]:
    """Convert archive ``bars_1m`` row → chart_bars / setups shape (t/o/h/l/c/v)."""
    ts = float(row.get("ts") or 0)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(_ET)
    return {
        "t": dt.isoformat(),
        "o": float(row.get("open") or 0),
        "h": float(row.get("high") or 0),
        "l": float(row.get("low") or 0),
        "c": float(row.get("close") or 0),
        "v": float(row.get("volume") or 0),
        "ts": ts,
    }


def _candidate_from_bars(symbol: str, bars: list[dict[str, Any]], session_date: str) -> dict[str, Any]:
    """Minimal gapper-shaped candidate for decide() from archived bars."""
    if not bars:
        return {
            "symbol": symbol,
            "price": None,
            "change_pct": None,
            "volume": 0,
            "rvol": None,
            "session_date": session_date,
            "source": "archive_replay",
        }
    last = bars[-1]
    first = bars[0]
    price = float(last.get("c") or 0)
    open_px = float(first.get("o") or price) or price
    change_pct = ((price - open_px) / open_px * 100.0) if open_px else 0.0
    vol = sum(float(b.get("v") or 0) for b in bars)
    return {
        "symbol": symbol,
        "price": price,
        "last": price,
        "change_pct": change_pct,
        "gap_percent": change_pct,
        "volume": vol,
        "rvol": None,
        "float": None,
        "session_date": session_date,
        "source": "archive_replay",
    }


def symbols_for_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
) -> list[str]:
    bars = load_table_rows(session_date, "bars_1m", cold_dir=cold_dir)
    tape = load_table_rows(session_date, "tape_ibkr", cold_dir=cold_dir)
    syms = {str(r.get("symbol", "")).upper() for r in bars if r.get("symbol")}
    syms |= {str(r.get("symbol", "")).upper() for r in tape if r.get("symbol")}
    return sorted(s for s in syms if s)


def replay_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
    symbols: list[str] | None = None,
    mode: str = NOVA_OS_DEFAULT_MODE,
    max_symbols: int = ARCHIVE_REPLAY_MAX_SYMBOLS,
) -> dict[str, Any]:
    """
    Replay one archived day through decide(record=False).

    Returns ``{session_date, decisions, symbols, errors}``.
    """
    root = cold_dir or cold_root()
    day_dir = root / session_date / ARCHIVE_SCHEMA_VERSION
    if not day_dir.is_dir():
        return {
            "ok": False,
            "session_date": session_date,
            "error": f"missing cold day: {day_dir}",
            "decisions": [],
            "symbols": [],
        }

    bar_rows = load_table_rows(session_date, "bars_1m", cold_dir=root)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in bar_rows:
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue
        by_symbol.setdefault(sym, []).append(archive_bar_to_chart(row))

    for sym, series in by_symbol.items():
        series.sort(key=lambda b: float(b.get("ts") or 0))

    target = symbols or sorted(by_symbol.keys())
    if not target:
        # Fall back to tape-only symbols with empty bars
        target = symbols_for_day(session_date, cold_dir=root)
    target = [s.upper() for s in target][: max(1, int(max_symbols))]

    decisions: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for i, sym in enumerate(target):
        bars = by_symbol.get(sym, [])
        candidate = _candidate_from_bars(sym, bars, session_date)
        try:
            result = decide(
                candidate,
                bars,
                mode=mode,
                watchlist_rank=i + 1,
                articles=[],
                record=False,
            )
            payload = result.to_dict()
            payload["replay"] = {
                "session_date": session_date,
                "bar_count": len(bars),
                "source": ARCHIVE_SOURCE_IBKR,
            }
            decisions.append(payload)
        except Exception as exc:
            logger.exception("archive.replay: decide failed for %s", sym)
            errors.append({"symbol": sym, "error": str(exc)})

    return {
        "ok": not errors or bool(decisions),
        "session_date": session_date,
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "symbols": target,
        "decision_count": len(decisions),
        "decisions": decisions,
        "errors": errors,
        "record": False,
        "note": "Replay uses decide(record=False) — no receipts, no orders.",
    }
