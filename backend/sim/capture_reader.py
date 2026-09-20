"""Read capture event rows without accepting unusable market prices."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    dropped = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    dropped += 1
                    continue
                rows.append(row)
            except json.JSONDecodeError:
                dropped += 1
                continue
    if dropped:
        # D-067: a torn tail from an interrupted write is real data loss; say so
        # instead of silently replaying a short session.
        logger.warning(
            "CAPTURE replay: dropped %d unparseable line(s) from %s "
            "(truncated tail from an interrupted write?) — %d rows loaded",
            dropped,
            path,
            len(rows),
        )
    return rows



def usable_rows(rows: list[dict[str, Any]], kind: str, symbol: str) -> list[dict[str, Any]]:
    """Only time-stamped positive prices for the selected capture are usable."""
    def positive(value: Any) -> bool:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value > 0)

    accepted = []
    for row in rows:
        price = row.get("price") if kind == "prints" else row.get("last") or row.get("price")
        if not positive(row.get("ts")) or not positive(price):
            continue
        if str(row.get("symbol") or symbol).upper() != symbol.upper():
            continue
        accepted.append({**row, "symbol": symbol.upper()})
    if len(accepted) != len(rows):
        logger.warning("CAPTURE replay: dropped %d unusable %s rows", len(rows) - len(accepted), kind)
    return sorted(accepted, key=lambda row: row["ts"])
