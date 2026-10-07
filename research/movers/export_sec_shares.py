"""SEC shares outstanding, as each filing reported them, into the day movers store (ADR 050).

The float limit's second kind of evidence (AGENTS.md section 3: a float cannot exceed the shares outstanding).
From SEC's bulk ``companyfacts.zip`` (``NOVA_CATALYST_DIR``, default F:\\Nova\\catalysts\\edgar): every
``dei:EntityCommonStockSharesOutstanding`` a company reported, else us-gaap ``CommonStockSharesOutstanding``,
with the date it is as of and the date it was filed -- the search reads only what was filed by the session. A
company with several share classes reports several counts for one date: the largest is kept, so a limit is never
passed on one class's smaller count. Tickers come from the Massive reference's ``cik`` (today's dump, delisted
tickers included); a ticker another company used first reads the current owner's counts, which the as-of window
and the split list rarely let through. Replaces the whole table; run it again after a new companyfacts.zip.

Usage (from the repo root):
    py -3 research/movers/export_sec_shares.py [--zip PATH] [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "research" / "leaderboard"))
sys.path.insert(0, str(REPO / "backend"))

from lb_config import DATA_ROOT, REFERENCE_SUBDIR  # noqa: E402

from constants_day_movers import DAY_MOVERS_DB_FILENAME, DAY_MOVERS_SUBDIR  # noqa: E402
from day_movers import store  # noqa: E402

CATALYST_ROOT = Path(os.environ.get("NOVA_CATALYST_DIR") or r"F:\Nova\catalysts")
DEFAULT_ZIP = CATALYST_ROOT / "edgar" / "companyfacts.zip"
DEFAULT_DB = DATA_ROOT / DAY_MOVERS_SUBDIR / DAY_MOVERS_DB_FILENAME
CONCEPTS = (("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding"))


def cik_tickers(reference: Path) -> dict[str, list[str]]:
    """``cik (no leading zeros) -> tickers`` from the Massive reference dump."""
    out: dict[str, list[str]] = defaultdict(list)
    for row in json.loads(reference.read_text(encoding="utf-8")):
        symbol, cik = str(row.get("ticker") or "").strip(), str(row.get("cik") or "").lstrip("0")
        if symbol and cik and symbol not in out[cik]:
            out[cik].append(symbol)
    return out


def share_counts(facts: dict) -> list[tuple[str, str, float, str | None]]:
    """``(as_of, filed, shares, form)`` from the first concept a company reports, largest per (as_of, filed)."""
    for namespace, concept in CONCEPTS:
        units = facts.get(namespace, {}).get(concept, {}).get("units", {}).get("shares")
        if not units:
            continue
        best: dict[tuple[str, str], tuple[float, str | None]] = {}
        for unit in units:
            end, filed, value = unit.get("end"), unit.get("filed"), unit.get("val")
            if not end or not filed or not isinstance(value, (int, float)) or value <= 0:
                continue
            key = (str(end), str(filed))
            if key not in best or value > best[key][0]:
                best[key] = (float(value), unit.get("form"))
        return [(end, filed, shares, form) for (end, filed), (shares, form) in sorted(best.items())]
    return []


def export(zip_path: Path, db_path: Path, reference: Path) -> dict[str, int]:
    mapping = cik_tickers(reference)
    rows: list[dict] = []
    read = missing = 0
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        for cik, symbols in mapping.items():
            name = f"CIK{cik.zfill(10)}.json"
            if name not in names:
                missing += 1
                continue
            facts = json.loads(archive.read(name)).get("facts", {})
            read += 1
            for as_of, filed, shares, form in share_counts(facts):
                rows.extend({"symbol": s, "cik": cik, "as_of": as_of, "filed": filed, "shares": shares, "form": form}
                            for s in symbols)
    with store.connect(db_path) as db:
        written = store.replace_sec_shares(db, rows)
    return {"companies": len(mapping), "read": read, "not_in_zip": missing, "rows": written,
            "tickers": len({r["symbol"] for r in rows})}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--reference", type=Path, default=DATA_ROOT / REFERENCE_SUBDIR / "tickers.json")
    args = ap.parse_args(argv)
    started = time.time()
    counts = export(args.zip, args.db, args.reference)
    print(f"sec_shares: {counts['rows']:,} rows for {counts['tickers']:,} tickers from {counts['read']:,} of "
          f"{counts['companies']:,} companies ({counts['not_in_zip']:,} not in {args.zip.name}); "
          f"{time.time() - started:.0f} s -> {args.db}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
