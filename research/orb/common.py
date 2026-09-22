"""Shared paths, env loading and the DuckDB store for the ORB research harness.

Data root: the Massive flat files on the operator's F: drive (``NOVA_MARKET_DATA_DIR``
overrides). The store is one DuckDB file beside them. Nothing here touches the Nova
backend; this is offline research (AGENTS.md: vectorbt-style skills are research only).
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import duckdb

DATA_ROOT = Path(os.environ.get("NOVA_MARKET_DATA_DIR") or r"F:\Nova\data\massive")
MINUTE_DIR = DATA_ROOT / "minute_aggs_v1"
STORE_DIR = DATA_ROOT / "store"
DB_PATH = STORE_DIR / "orb.duckdb"
TZ = "America/New_York"

_DAY_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.csv\.gz$")


def load_env() -> None:
    """Load the desk .env (NOVA_ENV_PATH, else the first .env walking up from cwd)."""
    candidates = []
    if os.environ.get("NOVA_ENV_PATH"):
        candidates.append(Path(os.environ["NOVA_ENV_PATH"]))
    candidates += [p / ".env" for p in (Path.cwd(), *Path.cwd().parents)]
    for env in candidates:
        if env.is_file():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            return


def minute_files() -> dict[date, Path]:
    """Every downloaded minute file keyed by its trading date."""
    out: dict[date, Path] = {}
    for p in MINUTE_DIR.glob("*/*/*.csv.gz"):
        m = _DAY_RE.search(p.name)
        if m:
            out[date.fromisoformat(m.group(1))] = p
    return dict(sorted(out.items()))


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    con.execute("SET threads TO 8")
    return con


# One minute-file read, with the Eastern wall-clock time of each bar.
MINUTE_SOURCE_SQL = """
SELECT ticker, open, high, low, close, volume,
       (to_timestamp(window_start // 1000000000) AT TIME ZONE 'America/New_York')::TIME AS t
FROM read_csv(?, header = true,
              columns = {'ticker': 'VARCHAR', 'volume': 'BIGINT', 'open': 'DOUBLE', 'close': 'DOUBLE',
                         'high': 'DOUBLE', 'low': 'DOUBLE', 'window_start': 'BIGINT', 'transactions': 'BIGINT'})
"""
