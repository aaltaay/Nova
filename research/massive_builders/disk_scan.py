"""Which raw flat files and derived trades tables are whole on disk (read-only directory listings, for verify_all.py).

Raw layout: ``<NOVA_MARKET_DATA_DIR>/<dataset>/<year>/<month>/<day>.csv.gz`` (``.part`` while arriving, not counted).
Tables: ``<products_root>/trades_flow_v1|trades_movers_v1/<year>/<month>/<day>.parquet`` (``.tmp`` while written).
"""
from __future__ import annotations

import os

from massive_env import ROOT
from trades_products import products_root


def _entries(path) -> list:
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def whole_raw_files(ds: str) -> dict[str, int]:
    """{day: size} of the raw files of one dataset whole on disk."""
    done: dict[str, int] = {}
    for y in _entries(ROOT / ds):
        if not y.is_dir():
            continue
        for m in _entries(y.path):
            if not m.is_dir():
                continue
            for f in _entries(m.path):
                try:
                    if f.name.endswith(".csv.gz"):
                        done[f.name[:-7]] = f.stat().st_size
                except OSError:
                    continue                                    # renamed between the listing and the stat: the next scan has it
    return done


def table_days() -> tuple[set[str], set[str]]:
    """(days with the flow table, days with the movers table): our own derived tables."""
    base = products_root()
    flow: set[str] = set(); mov: set[str] = set()
    for sub, out in (("trades_flow_v1", flow), ("trades_movers_v1", mov)):
        for y in _entries(base / sub):
            if not y.is_dir():
                continue
            for m in _entries(y.path):
                if not m.is_dir():
                    continue
                for f in _entries(m.path):
                    if f.name.endswith(".parquet"):
                        out.add(f.name[:-8])
    return flow, mov
