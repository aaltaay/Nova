"""
Replay archived tape/bars through ``nova_os.decide`` (P9).

Loads a cold day (JSONL), builds per-symbol candidates + chart-shaped bars,
calls ``decide(..., record=False)``, and returns collected decisions.
Never places orders; never writes receipts.

No-hindsight contract (2026-07-15 hardening): ``decide()`` must only ever see
bars that existed at the moment being replayed. ``replay_at``/``walk_day``
slice each symbol's bar series to ``ts <= as_of_ts`` before building a
candidate or calling ``decide()`` — a decision "as of 9:41 ET" can never see
the 9:42 bar, let alone the day's close. ``replay_day()`` without an explicit
``as_of_ts`` keeps its original whole-day behavior for backward compatibility
(existing CLI/route callers), but is now explicitly marked ``hindsight: True``
in its response so nobody mistakes it for a fair simulation — prefer
``replay_at`` or ``walk_day`` for anything that claims to test decision
quality.
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
    ARCHIVE_REPLAY_WALK_MAX_STEPS,
    ARCHIVE_REPLAY_WALK_STEP_MIN,
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


def slice_bars_as_of(bars: list[dict[str, Any]], as_of_ts: float) -> list[dict[str, Any]]:
    """Bars with ``ts <= as_of_ts`` only — the no-hindsight boundary. ``bars``
    must already be sorted ascending by ``ts`` (true for anything returned by
    ``bars_by_symbol_for_day``)."""
    return [b for b in bars if float(b.get("ts") or 0) <= as_of_ts]


def _decide_snapshot(
    by_symbol: dict[str, list[dict[str, Any]]],
    target: list[str],
    session_date: str,
    *,
    as_of_ts: float | None,
    mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """One decide() call per symbol in ``target``, using only bars with
    ``ts <= as_of_ts`` (or the full day when ``as_of_ts`` is None — hindsight,
    caller's explicit choice, never the default for a "fair" replay)."""
    decisions: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for i, sym in enumerate(target):
        full_bars = by_symbol.get(sym, [])
        bars = full_bars if as_of_ts is None else slice_bars_as_of(full_bars, as_of_ts)
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
                "as_of_ts": as_of_ts,
                "bar_count": len(bars),
                "hindsight": as_of_ts is None,
                "source": ARCHIVE_SOURCE_IBKR,
            }
            decisions.append(payload)
        except Exception as exc:
            logger.exception("archive.replay: decide failed for %s", sym)
            errors.append({"symbol": sym, "error": str(exc)})
    return decisions, errors


def _resolve_target_symbols(
    by_symbol: dict[str, list[dict[str, Any]]],
    session_date: str,
    symbols: list[str] | None,
    max_symbols: int,
    *,
    cold_dir: Path | None,
) -> list[str]:
    target = symbols or sorted(by_symbol.keys())
    if not target:
        # Fall back to tape-only symbols with empty bars
        target = symbols_for_day(session_date, cold_dir=cold_dir)
    return [s.upper() for s in target][: max(1, int(max_symbols))]


def replay_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
    symbols: list[str] | None = None,
    mode: str = NOVA_OS_DEFAULT_MODE,
    max_symbols: int = ARCHIVE_REPLAY_MAX_SYMBOLS,
    as_of_ts: float | None = None,
) -> dict[str, Any]:
    """
    Replay one archived day through decide(record=False).

    Without ``as_of_ts`` this feeds decide() the *entire* day's bars per
    symbol — the response is marked ``"hindsight": True`` and must not be
    treated as evidence of decision quality (kept only for the existing
    CLI/route default). Pass ``as_of_ts`` (or call ``replay_at``) to get a
    single fair, no-hindsight decision snapshot instead.

    Returns ``{session_date, decisions, symbols, errors, hindsight}``.
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

    by_symbol = bars_by_symbol_for_day(session_date, cold_dir=root)
    target = _resolve_target_symbols(by_symbol, session_date, symbols, max_symbols, cold_dir=root)
    decisions, errors = _decide_snapshot(by_symbol, target, session_date, as_of_ts=as_of_ts, mode=mode)

    return {
        "ok": not errors or bool(decisions),
        "session_date": session_date,
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "symbols": target,
        "decision_count": len(decisions),
        "decisions": decisions,
        "errors": errors,
        "record": False,
        "as_of_ts": as_of_ts,
        "hindsight": as_of_ts is None,
        "note": (
            "Replay uses decide(record=False) — no receipts, no orders. "
            + (
                "hindsight=True: decide() saw the WHOLE day's bars for a single "
                "decision — not a fair simulation. Pass as_of_ts (or use "
                "replay_at/walk_day) for a no-hindsight snapshot."
                if as_of_ts is None
                else "hindsight=False: decide() only saw bars up to as_of_ts."
            )
        ),
    }


def replay_at(
    session_date: str,
    as_of_ts: float,
    *,
    cold_dir: Path | None = None,
    symbols: list[str] | None = None,
    mode: str = NOVA_OS_DEFAULT_MODE,
    max_symbols: int = ARCHIVE_REPLAY_MAX_SYMBOLS,
) -> dict[str, Any]:
    """No-hindsight point-in-time replay — decide() sees only bars with
    ``ts <= as_of_ts``. Thin, explicitly-named wrapper over replay_day() so
    callers can't forget the flag."""
    return replay_day(
        session_date,
        cold_dir=cold_dir,
        symbols=symbols,
        mode=mode,
        max_symbols=max_symbols,
        as_of_ts=as_of_ts,
    )


def _walk_steps(by_symbol: dict[str, list[dict[str, Any]]], target: list[str], step_sec: float) -> list[float]:
    all_ts = [
        float(b.get("ts") or 0)
        for sym in target
        for b in by_symbol.get(sym, [])
    ]
    if not all_ts:
        return []
    start, end = min(all_ts), max(all_ts)
    steps: list[float] = []
    t = start
    while t <= end:
        steps.append(t)
        t += step_sec
    if steps[-1] != end:
        steps.append(end)
    return steps


def walk_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
    symbols: list[str] | None = None,
    mode: str = NOVA_OS_DEFAULT_MODE,
    max_symbols: int = ARCHIVE_REPLAY_MAX_SYMBOLS,
    step_min: float = ARCHIVE_REPLAY_WALK_STEP_MIN,
    max_steps: int = ARCHIVE_REPLAY_WALK_MAX_STEPS,
) -> dict[str, Any]:
    """
    Walk one archived day in ``step_min`` increments, calling decide() at
    each as-of point with only the bars that existed by then. This is the
    "rewind" backbone: the returned ``steps`` list is a scrubbable timeline —
    a caller can jump to any index to see exactly what Nova OS would have
    decided at that moment, with no lookahead into later steps.

    Returns ``{session_date, step_min, steps: [{as_of_ts, as_of_iso,
    decisions, errors}, ...], symbols, hindsight: False}``.
    """
    root = cold_dir or cold_root()
    day_dir = root / session_date / ARCHIVE_SCHEMA_VERSION
    if not day_dir.is_dir():
        return {
            "ok": False,
            "session_date": session_date,
            "error": f"missing cold day: {day_dir}",
            "steps": [],
            "symbols": [],
        }

    by_symbol = bars_by_symbol_for_day(session_date, cold_dir=root)
    target = _resolve_target_symbols(by_symbol, session_date, symbols, max_symbols, cold_dir=root)
    step_sec = max(1.0, float(step_min)) * 60.0
    as_of_points = _walk_steps(by_symbol, target, step_sec)[: max(1, int(max_steps))]

    steps: list[dict[str, Any]] = []
    for as_of_ts in as_of_points:
        decisions, errors = _decide_snapshot(by_symbol, target, session_date, as_of_ts=as_of_ts, mode=mode)
        steps.append({
            "as_of_ts": as_of_ts,
            "as_of_iso": datetime.fromtimestamp(as_of_ts, tz=timezone.utc).astimezone(_ET).isoformat(),
            "decisions": decisions,
            "errors": errors,
        })

    return {
        "ok": bool(steps),
        "session_date": session_date,
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "step_min": step_min,
        "step_count": len(steps),
        "symbols": target,
        "steps": steps,
        "hindsight": False,
        "record": False,
        "note": "Walk uses decide(record=False) at each as_of step — no receipts, no orders, no lookahead.",
    }
