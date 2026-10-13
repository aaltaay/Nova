"""Split Massive's FINRA short-interest dump into one file per settlement month.

``massive_reference_dump.py`` writes every settlement into one ``store/reference/short_interest.jsonl``
(about 500 MB from 2017 on). The backend reads a stock's short interest as published by a past moment
(``backend/move_reason/short_interest.py``, the Sim's "Why it's moving") from
``store/reference/short_interest/<YYYY-MM>.jsonl`` instead -- the settlement's month and the two before it,
a few MB each, so a playhead read never scans the whole dump. Rows are copied as they are.

Each month is written to ``<YYYY-MM>.jsonl.tmp`` and moved into place once the whole dump is read, so a reader
never sees half a month; a month the dump does not hold is left as it is. No duckdb: this runs anywhere.

Usage:
    py -3 research/orb/short_interest_months.py            # <NOVA_MARKET_DATA_DIR>/store/reference
    py -3 research/orb/short_interest_months.py --ref DIR
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import IO

FLAT = "short_interest.jsonl"
MONTHS = "short_interest"


def reference_dir() -> Path:
    return Path(os.environ.get("NOVA_MARKET_DATA_DIR") or r"E:\Nova\massive") / "store" / "reference"


def needs_split(ref: Path) -> bool:
    """The dump exists and its months are missing or older than it."""
    flat, out = ref / FLAT, ref / MONTHS
    if not flat.is_file():
        return False
    months = list(out.glob("*.jsonl")) if out.is_dir() else []
    return not months or max(p.stat().st_mtime for p in months) < flat.stat().st_mtime


def split_by_month(ref: Path) -> dict[str, int]:
    """Rows written per settlement month (``YYYY-MM``); ``"skipped"`` counts rows with no settlement date."""
    out = ref / MONTHS
    out.mkdir(parents=True, exist_ok=True)
    handles: dict[str, IO[str]] = {}
    counts: dict[str, int] = {"skipped": 0}
    try:
        with (ref / FLAT).open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                settled = str(json.loads(line).get("settlement_date") or "")
                month = settled[:7]
                if len(month) != 7 or month[4] != "-":
                    counts["skipped"] += 1
                    continue
                if month not in handles:
                    handles[month] = (out / f"{month}.jsonl.tmp").open("w", encoding="utf-8")
                handles[month].write(line if line.endswith("\n") else line + "\n")
                counts[month] = counts.get(month, 0) + 1
    finally:
        for h in handles.values():
            h.close()
    for month in handles:
        os.replace(out / f"{month}.jsonl.tmp", out / f"{month}.jsonl")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", type=Path, default=None, help="the reference folder (default: under NOVA_MARKET_DATA_DIR)")
    a = ap.parse_args()
    ref = a.ref or reference_dir()
    if not (ref / FLAT).is_file():
        print(f"no {FLAT} under {ref}")
        return 1
    counts = split_by_month(ref)
    months = sorted(k for k in counts if k != "skipped")
    print(f"{len(months)} months ({months[0] if months else '-'} .. {months[-1] if months else '-'}), "
          f"{sum(counts[m] for m in months)} rows, {counts['skipped']} without a settlement date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
