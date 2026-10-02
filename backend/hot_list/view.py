"""``GET /api/hot-list`` (ADR 043): today's list as the Bots page reads it. Memory and one small file; no wait.

``{schema_version: 1, date, cap, auto: {n, start, end, rule, error}, default, entries: [{symbol, how, at,
board, rank, change_pct, followed, why_not_followed}], yesterday, error}`` -- ``followed`` is whether the
setup scanner reads the stock now (its universe), ``null`` when the scanner cannot be read, and
``why_not_followed`` says why whenever it is not ``true`` ("HOD Momo's 20 reserved slots are full" for a
listed name past the block it shares with Former Momo; ``hot_list.following``). Before the 04:00 rollover
has run, the view is the rolled list (``service.peek``): empty, with the last day's names as ``yesterday``.
"""
from __future__ import annotations

import time
from typing import Any

from constants_hot_list import HOT_LIST_AUTO_END_ET, HOT_LIST_AUTO_START_ET, HOT_LIST_CAP, HOT_LIST_SCHEMA_VERSION
from hot_list import auto, following, service


def _entry(entry: dict[str, Any], followed_now: set[str] | None) -> dict[str, Any]:
    followed, why = following.status(entry["symbol"], followed_now)
    return {**entry, "followed": followed, "why_not_followed": why}


def build(now: float | None = None) -> dict[str, Any]:
    ts = time.time() if now is None else float(now)
    doc, error = service.peek(ts)
    followed_now = following.universe()
    entries = [_entry(entry, followed_now) for entry in doc.get("entries") or []]
    n = int(doc.get("auto_n") or 0)
    return {
        "schema_version": HOT_LIST_SCHEMA_VERSION,
        "date": doc["date"],
        "cap": HOT_LIST_CAP,
        "auto": {"n": n, "start": HOT_LIST_AUTO_START_ET, "end": HOT_LIST_AUTO_END_ET, "rule": auto.rule_text(n),
                 "error": auto.status()["error"]},
        "default": dict(doc["default"]),
        "entries": entries,
        "yesterday": list(doc.get("yesterday") or []),
        "error": error,
    }
