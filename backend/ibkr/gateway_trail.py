"""Append-only Paper/Live door trail.

Owner: this module (read + write).
Invalidation: append-only; trimmed to IBKR_GATEWAY_TRAIL_MAX_EVENTS.
schema_version: SCHEMA_VERSION (load skips unknown / corrupt lines).

Not Nova OS decide() and not the execution ledger. Those are orders/verdicts.
This answers: who requested a door, what plan ran, and whether the IB
account class actually matched.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from constants_ibkr import IBKR_GATEWAY_TRAIL_FILENAME, IBKR_GATEWAY_TRAIL_MAX_EVENTS
from paths import cache_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def trail_path() -> Path:
    return cache_dir() / IBKR_GATEWAY_TRAIL_FILENAME


def append_event(
    *,
    actor: str,
    event: str,
    requested: str | None = None,
    kind_before: str | None = None,
    kind_after: str | None = None,
    plan: str | None = None,
    launch_action: str | None = None,
    switched: bool | None = None,
    note: str | None = None,
) -> None:
    """Best-effort append. Must not break connect / switch paths."""
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ts": time.time(),
        "actor": str(actor),
        "event": str(event),
    }
    if requested is not None:
        row["requested"] = requested
    if kind_before is not None:
        row["kind_before"] = kind_before
    if kind_after is not None:
        row["kind_after"] = kind_after
    if plan is not None:
        row["plan"] = plan
    if launch_action is not None:
        row["launch_action"] = launch_action
    if switched is not None:
        row["switched"] = bool(switched)
    if note:
        row["note"] = str(note)[:240]
    try:
        path = trail_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        _trim(path)
    except Exception:
        logger.warning("IBKR: gateway trail append failed", exc_info=True)


def recent(limit: int = 40) -> list[dict[str, Any]]:
    """Oldest-first slice of the newest ``limit`` valid rows."""
    path = trail_path()
    if not path.is_file():
        return []
    cap = max(1, min(int(limit), IBKR_GATEWAY_TRAIL_MAX_EVENTS))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:  # maintainer: allow-swallow a diagnostics trail, logged; no account or order state rides on it
        logger.warning("IBKR: gateway trail read failed", exc_info=True)
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("schema_version") != SCHEMA_VERSION:
            continue
        if not obj.get("event") or not obj.get("actor"):
            continue
        rows.append(obj)
    return rows[-cap:]


def _trim(path: Path) -> None:
    max_n = int(IBKR_GATEWAY_TRAIL_MAX_EVENTS)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    if len(lines) <= max_n:
        return
    keep = [ln for ln in lines[-max_n:] if ln.strip()]
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")
