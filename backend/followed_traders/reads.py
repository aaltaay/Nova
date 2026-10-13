"""One trader's reads between two times, from the feed's read log (``feed.parse_reads``). Pure.

The log has a line each time any read changed, so a trader's read is folded: consecutive lines that read this trader
the same way are one read, from the first line's time until the next read began. A line without the name is
``seen: false`` (the bar was off screen, or the name tag read as something else). Shapes:
architecture/schema/followed-traders.md (``GET /api/followed-traders/reads``).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def clock_ts(date: str, clock: str) -> float:
    """``HH:MM:SS`` on the screen's ET clock that day, as epoch seconds."""
    return datetime.fromisoformat(f"{date}T{clock}").replace(tzinfo=ET).timestamp()


def trader_reads(log: list[dict[str, Any]], *, date: str, trader: str, from_ts: float, to_ts: float,
                 max_reads: int) -> dict[str, Any]:
    """``{reads, truncated}``: the read in force at ``from_ts``, then each read that began by ``to_ts``."""
    folded: list[dict[str, Any]] = []
    for line in log:
        got = line["traders"].get(trader)
        read = {"seen": got is not None,
                "positions": [dict(p) for p in got["positions"]] if got else [],
                "unparsed": list(got["unparsed"]) if got else []}
        if folded and _same(folded[-1], read):
            continue
        ts = clock_ts(date, line["clock"])
        if folded:
            folded[-1]["until_ts"] = ts
        folded.append({"ts": ts, "until_ts": None, **read})
    window = [r for r in folded if r["ts"] <= to_ts and (r["until_ts"] is None or r["until_ts"] > from_ts)]
    return {"reads": window[:max_reads], "truncated": len(window) > max_reads}


def _same(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a["seen"], a["positions"], a["unparsed"]) == (b["seen"], b["positions"], b["unparsed"])
