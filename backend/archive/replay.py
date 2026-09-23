"""
Read archived cold days: table rows, chart-shaped 1m bars, the no-hindsight slice.

The ``decide()`` replay (``replay_day`` / ``replay_at`` / ``walk_day``) was
retired with the Nova OS verdict (ADR 025). What stays is used by the backtest
engine (``bars_by_symbol_for_day`` + ``slice_bars_as_of``) and ``archive.ask``
(``load_table_rows`` + ``symbols_for_day``).

Interval-close contract (#385): an archived bar's ``ts`` is the minute's
OPENING stamp, so a bar counts as known only from ``ts + interval`` onward
(inclusive at close) -- ``slice_bars_as_of`` never reveals an in-progress
minute's final high/close/volume.
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
    ARCHIVE_BAR_1M_INTERVAL_SEC,
    ARCHIVE_SCHEMA_VERSION,
)

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


def bars_by_symbol_for_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Full-day chart-shaped bars per symbol, each series sorted ascending by
    ``ts``. Callers that must not see the whole day (i.e. any decision-making
    path) should slice with ``slice_bars_as_of`` before use — this function
    itself carries no time boundary."""
    bar_rows = load_table_rows(session_date, "bars_1m", cold_dir=cold_dir)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in bar_rows:
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue
        by_symbol.setdefault(sym, []).append(archive_bar_to_chart(row))
    for series in by_symbol.values():
        series.sort(key=lambda b: float(b.get("ts") or 0))
    return by_symbol


def slice_bars_as_of(
    bars: list[dict[str, Any]],
    as_of_ts: float,
    *,
    bar_interval_sec: float = ARCHIVE_BAR_1M_INTERVAL_SEC,
) -> list[dict[str, Any]]:
    """Bars whose interval has CLOSED by ``as_of_ts`` — the no-hindsight
    boundary.

    Interval-close contract: a bar's ``ts`` is its OPENING stamp, but its
    high/low/close/volume are only known once the interval has ended, so a bar
    is visible iff ``ts + bar_interval_sec <= as_of_ts``. The boundary is
    inclusive at close (a bar opening at ``t`` is visible at ``t + interval``,
    not before), which is the same rule ``sim/chart_replay`` already applies.
    An in-progress minute's final high, close and volume are never revealed
    early. ``bars`` must already be sorted ascending by ``ts`` (true for
    anything returned by ``bars_by_symbol_for_day``).
    """
    return [b for b in bars if float(b.get("ts") or 0) + bar_interval_sec <= as_of_ts]
