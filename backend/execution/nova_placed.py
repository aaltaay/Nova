"""Persist Nova click/send ISO on the execution ledger (Orders Today Time Placed).

Owner: execution.nova_placed (write) + closed_blotter / fill_audit_attach (read).
Invalidation: first stamp wins; never overwrite a later click.
schema_version: lives on executions.payload_json (ledger schema).

RAM ``remember_nova_placed`` is still the intra-process fallback. This module
is the restart-safe copy. Do not invent a browser clock.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def persist_nova_placed_at(execution_id: str, iso: str | None) -> str | None:
    """Write payload.nova_placed_at. First stamp wins. Safe if the row is missing."""
    if not execution_id:
        return None
    stamp = str(iso or "").strip()
    if not stamp:
        return None
    try:
        from execution import evidence_store
        from execution import store

        row = store.get_by_id(str(execution_id))
        if not row:
            return None
        payload = dict(row.get("payload") or {})
        existing = str(payload.get("nova_placed_at") or "").strip()
        if existing:
            return existing
        evidence_store.merge_execution_payload(
            str(execution_id), {"nova_placed_at": stamp}
        )
        return stamp
    except Exception:
        logger.exception(
            "nova_placed: persist failed for execution_id=%s", execution_id
        )
        return None


def ledger_placed_iso(led: dict[str, Any] | None) -> str | None:
    """Broker overlay fallback: persisted send ISO, else honest created_ts."""
    if not led:
        return None
    payload = led.get("payload") or {}
    stamp = str(payload.get("nova_placed_at") or "").strip()
    if stamp:
        return stamp
    try:
        ts = float(led.get("created_ts") or 0)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
