"""Export a committed HOD Momo replay fixture from the local archive.

Reads the local (untracked) archive hot store + dated scanner caches and
emits a compact, deterministic fixture under ``backend/tests/fixtures/hod_replay``
so the replay harness and golden tests can run offline in CI:

- ``tape-<date>.jsonl``  -- IBKR tape prints (symbol, ts, price, size), ts-ordered
- ``bars-<date>.jsonl``  -- 1m bars (symbol, ts, open/high/low/close/volume)
- ``meta-<date>.json``   -- per-symbol fundamentals stand-ins (prev_close, float
  from the movers cache), production alerts for the parity test, and capture
  coverage notes (prints per symbol) so fidelity caveats travel with the data.

Usage:
    py -3 tools/export_hod_replay_fixture.py --date 2026-07-17

Deterministic: same archive inputs -> byte-identical outputs. Writes are
atomic (tmp + replace). Read-only with respect to the archive itself.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = os.path.join(_REPO_ROOT, "backend", ".cache", "archive.db")
_DEFAULT_CACHE = os.path.join(_REPO_ROOT, "backend", ".cache")
_DEFAULT_OUT = os.path.join(
    _REPO_ROOT, "backend", "tests", "fixtures", "hod_replay"
)

_META_ALERT_FIELDS = (
    "id",
    "timestamp",
    "ticker",
    "strategy_id",
    "strategy_name",
    "price",
    "change_pct",
    "rvol",
    "float_shares",
    "gap_pct",
    "volume",
    "momentum_pct",
    "created_ts",
)


def _atomic_write(path: str, payload: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".hod_replay_", dir=os.path.dirname(path)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_tape(db: sqlite3.Connection, date: str) -> list[dict]:
    rows = db.execute(
        "SELECT symbol, ts, price, size FROM tape_ibkr "
        "WHERE session_date = ? ORDER BY ts, id",
        (date,),
    ).fetchall()
    return [
        {
            "symbol": str(r[0]),
            "ts": float(r[1]),
            "price": float(r[2]),
            "size": float(r[3]),
        }
        for r in rows
    ]


def _load_bars(db: sqlite3.Connection, date: str) -> list[dict]:
    rows = db.execute(
        "SELECT symbol, ts, open, high, low, close, volume FROM bars_1m "
        "WHERE session_date = ? ORDER BY ts, id",
        (date,),
    ).fetchall()
    return [
        {
            "symbol": str(r[0]),
            "ts": float(r[1]),
            "open": float(r[2]),
            "high": float(r[3]),
            "low": float(r[4]),
            "close": float(r[5]),
            "volume": float(r[6]),
        }
        for r in rows
    ]


def _load_movers_meta(cache_dir: str, date: str) -> dict[str, dict]:
    """prev_close / float stand-ins from the end-of-day movers cache."""
    path = os.path.join(cache_dir, f"movers-{date}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for key in ("gainers", "losers"):
        for row in data.get(key) or []:
            sym = str(row.get("symbol") or "").upper()
            if not sym or sym in out:
                continue
            out[sym] = {
                "prev_close": row.get("prev_close"),
                "float_shares": row.get("float"),
                "gap_pct_snapshot": row.get("gap_percent"),
                "change_pct_snapshot": row.get("change_pct"),
                "snapshot_ts": data.get("ts"),
            }
    return out


def _load_production_alerts(cache_dir: str, date: str) -> list[dict]:
    path = os.path.join(cache_dir, f"hod-momo-{date}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    alerts = []
    for raw in data.get("alerts") or []:
        if not isinstance(raw, dict):
            continue
        alerts.append(
            {k: raw.get(k) for k in _META_ALERT_FIELDS if k in raw}
        )
    alerts.sort(key=lambda a: (float(a.get("created_ts") or 0.0), str(a.get("id"))))
    return alerts


def export_fixture(date: str, db_path: str, cache_dir: str, out_dir: str) -> dict:
    db = sqlite3.connect(db_path)
    try:
        tape = _load_tape(db, date)
        bars = _load_bars(db, date)
    finally:
        db.close()
    if not tape:
        raise SystemExit(f"no tape_ibkr rows for session_date={date}")

    movers = _load_movers_meta(cache_dir, date)
    production_alerts = _load_production_alerts(cache_dir, date)

    tape_symbols: dict[str, int] = {}
    for row in tape:
        tape_symbols[row["symbol"]] = tape_symbols.get(row["symbol"], 0) + 1

    symbols_meta: dict[str, dict] = {}
    for sym in sorted(tape_symbols):
        entry: dict = {"tape_prints": tape_symbols[sym]}
        entry.update(movers.get(sym) or {})
        fired = sorted(
            {int(a["strategy_id"]) for a in production_alerts if a.get("ticker") == sym}
        )
        entry["production_strategy_ids"] = fired
        symbols_meta[sym] = entry

    meta = {
        "session_date": date,
        "tape_rows": len(tape),
        "bars_rows": len(bars),
        "symbols": symbols_meta,
        "production_alerts": production_alerts,
        "notes": [
            "tape_ibkr only records symbols with an active tape subscription; "
            "symbols evaluated via L1-only ticks are not fully represented.",
            "float/prev_close are end-of-day movers-cache stand-ins; "
            "avg_volume and live enrichment snapshots were not archived.",
        ],
    }

    tape_payload = "".join(
        json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in tape
    )
    bars_payload = "".join(
        json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in bars
    )
    meta_payload = json.dumps(meta, indent=2, sort_keys=True) + "\n"

    tape_path = os.path.join(out_dir, f"tape-{date}.jsonl")
    bars_path = os.path.join(out_dir, f"bars-{date}.jsonl")
    meta_path = os.path.join(out_dir, f"meta-{date}.json")
    _atomic_write(tape_path, tape_payload)
    _atomic_write(bars_path, bars_payload)
    _atomic_write(meta_path, meta_payload)
    return {
        "tape_path": tape_path,
        "bars_path": bars_path,
        "meta_path": meta_path,
        "tape_rows": len(tape),
        "bars_rows": len(bars),
        "symbols": sorted(tape_symbols),
        "production_alerts": len(production_alerts),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, help="session date YYYY-MM-DD")
    parser.add_argument("--archive-db", default=_DEFAULT_DB)
    parser.add_argument("--cache-dir", default=_DEFAULT_CACHE)
    parser.add_argument("--out", default=_DEFAULT_OUT)
    args = parser.parse_args(argv)

    summary = export_fixture(args.date, args.archive_db, args.cache_dir, args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
