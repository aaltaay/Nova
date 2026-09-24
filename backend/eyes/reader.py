"""Read the eyes' journal (ADR 029). Pure over the files: nothing here writes.

``days()`` lists the journal's days; ``lines()`` streams one day's lines with
filters (a line of an unknown ``schema_version`` or unreadable JSON is skipped
and counted, never guessed); ``setups()`` folds a day's lines into one record
per setup a lane armed -- levels, grade, filter, tape at near and trigger,
proposals, score -- the shape an analysis starts from.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from constants_eyes import EYES_SCHEMA_VERSION


def days(folder: Path) -> list[dict[str, Any]]:
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.jsonl"), reverse=True):
        out.append({"date": path.stem, "bytes": path.stat().st_size, "path": str(path)})
    return out


def lines(path: Path, *, source: str | None = None, symbol: str | None = None, template: str | None = None,
          event: str | None = None, skipped: dict[str, int] | None = None) -> Iterator[dict[str, Any]]:
    """Journal lines of ``path`` matching every filter given (``event`` may be a comma list)."""
    events = set(event.split(",")) if event else None
    counts = skipped if skipped is not None else {}
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                counts["unreadable"] = counts.get("unreadable", 0) + 1
                continue
            if row.get("schema_version") != EYES_SCHEMA_VERSION:
                counts["unknown_schema"] = counts.get("unknown_schema", 0) + 1
                continue
            if source and row.get("source") != source:
                continue
            if symbol and (row.get("symbol") or "").upper() != symbol.upper():
                continue
            if template and row.get("template") != template:
                continue
            if events and row.get("event") not in events:
                continue
            yield row


def setups(rows: Iterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per (source, template, setup_id), in the order they armed."""
    out: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        sid = row.get("setup_id")
        if not sid:
            continue
        key = (row.get("source"), row.get("template"), sid)
        rec = out.get(key)
        if rec is None:
            rec = out[key] = {"source": row.get("source"), "template": row.get("template"), "rev": row.get("rev"),
                              "setup_id": sid, "symbol": row.get("symbol"), "date": row.get("date"),
                              "replay": row.get("replay"), "events": [], "bot": row.get("bot")}
        ev = row.get("event")
        rec["events"].append({"event": ev, "ts": row.get("ts"), "verdict": row.get("verdict"),
                              "status": row.get("status"), "reason": row.get("reason")})
        if ev in ("armed", "filtered"):
            rec.update(armed_ts=row.get("ts"), setup=row.get("setup"), grade=row.get("grade"),
                       pillars=row.get("pillars"))
            if ev == "filtered":
                rec["filtered"] = row.get("reason")
        elif ev == "rearmed":
            rec["setup"] = row.get("setup")
        elif ev == "near":
            rec.setdefault("near_ts", row.get("ts"))
            if row.get("tape"):
                rec.setdefault("near_tape", (row.get("tape") or {}).get("verdict"))
        elif ev == "triggered":
            rec.update(triggered_ts=row.get("ts"), trigger_tape=(row.get("tape") or {}).get("verdict"),
                       entry=(row.get("setup") or {}).get("entry"))
        elif ev in ("failed", "disarmed"):
            rec[f"{ev}_ts"] = row.get("ts")
            rec[f"{ev}_reason"] = row.get("reason")
        elif ev == "proposal":
            rec.setdefault("proposals", []).append({"status": row.get("status"), "ts": row.get("ts")})
        elif ev == "scored":
            rec.update(outcome=row.get("outcome"), bar_r=row.get("bar_r"), exit_reason=row.get("exit_reason"),
                       mfe=row.get("mfe"), mae=row.get("mae"))
    return list(out.values())


def counts(rows: Iterator[dict[str, Any]]) -> dict[str, Any]:
    """Events by kind, symbols seen, and tape verdicts, per (source, template)."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row.get('source')}:{row.get('template') or '-'}"
        bucket = out.setdefault(key, {"events": {}, "symbols": set(), "tape": {}})
        ev = row.get("event") or "?"
        bucket["events"][ev] = bucket["events"].get(ev, 0) + 1
        if row.get("symbol"):
            bucket["symbols"].add(row["symbol"])
        if ev == "tape":
            verdict = row.get("verdict") or "?"
            bucket["tape"][verdict] = bucket["tape"].get(verdict, 0) + 1
    return {k: {**v, "symbols": sorted(v["symbols"])} for k, v in out.items()}
