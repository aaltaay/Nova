"""
Append-only Nova OS event store + no-silent-action receipts (Phase P1).

The audit contract: every Nova OS decision or action produces exactly one
persisted event and a returned receipt dict — nothing Nova OS does is silent.
This module owns writing those rows and reading them back. It intentionally
exposes NO update or delete (append-only); history is immutable here.

`record_receipt()` is the one write path. It validates every code against the
stable vocabulary in `codes.py` and fails closed (ValueError) on an unknown
code rather than poisoning the audit log with a typo'd verdict/action/reason.
Decision logic does not live here — decide() (P2) will call record_receipt().
"""
from __future__ import annotations

import json
import logging
import time

from constants import NOVA_OS_EVENTS_DEFAULT_LIMIT

logger = logging.getLogger(__name__)
from nova_os import codes
from nova_os.events_db import get_connection

# Event "kind" — a coarse category for filtering the log. Free-form on purpose
# (decision vs action vs system note); the structured columns carry the detail.
KIND_DECISION = "decision"
KIND_ACTION = "action"
KIND_SYSTEM = "system"


def record_receipt(
    *,
    kind: str,
    symbol: str | None = None,
    decision: str | None = None,
    action: str | None = None,
    mode: str | None = None,
    reason_codes: list[str] | None = None,
    would_execute: bool = False,
    executed: bool = False,
    payload: dict | None = None,
) -> dict:
    """Append one immutable event and return it as a receipt.

    Fails closed (ValueError) if any provided decision / action / mode / reason
    code is outside the stable vocabulary, so the audit log can never record a
    code the UI or a future decide() cannot interpret. `would_execute` records
    intent; `executed` records that a broker action actually happened — both are
    stored so a receipt can never imply an action that did not occur.
    """
    reasons = reason_codes or []
    if decision is not None and not codes.is_valid_decision(decision):
        raise ValueError(f"unknown Nova OS decision: {decision!r}")
    if action is not None and not codes.is_valid_action(action):
        raise ValueError(f"unknown Nova OS action: {action!r}")
    if mode is not None and not codes.is_valid_mode(mode):
        raise ValueError(f"unknown Nova OS mode: {mode!r}")
    invalid = codes.validate_reason_codes(reasons)
    if invalid:
        raise ValueError(f"unknown Nova OS reason code(s): {invalid}")

    ts = time.time()
    policy_version = codes.policy_version()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO events (
                ts, policy_version, kind, symbol, decision, action, mode,
                reason_codes, would_execute, executed, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                policy_version,
                kind,
                symbol,
                decision,
                action,
                mode,
                json.dumps(reasons),
                int(would_execute),
                int(executed),
                json.dumps(payload or {}),
            ),
        )
        conn.commit()
        event_id = int(cur.lastrowid)
    finally:
        conn.close()

    receipt = {
        "id": event_id,
        "ts": ts,
        "policy_version": policy_version,
        "kind": kind,
        "symbol": symbol,
        "decision": decision,
        "action": action,
        "mode": mode,
        "reason_codes": reasons,
        "would_execute": would_execute,
        "executed": executed,
        "payload": payload or {},
    }
    try:
        from alerts.hooks import notify_nova_os_event
    except ImportError:
        logger.debug("Nova OS: alerts hooks unavailable for receipt notify")
    else:
        notify_nova_os_event(receipt)
    return receipt


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "ts": row["ts"],
        "policy_version": row["policy_version"],
        "kind": row["kind"],
        "symbol": row["symbol"],
        "decision": row["decision"],
        "action": row["action"],
        "mode": row["mode"],
        "reason_codes": json.loads(row["reason_codes"] or "[]"),
        "would_execute": bool(row["would_execute"]),
        "executed": bool(row["executed"]),
        "payload": json.loads(row["payload_json"] or "{}"),
    }


def get_events(
    limit: int = NOVA_OS_EVENTS_DEFAULT_LIMIT,
    symbol: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    """Read recent events newest-first, optionally filtered by symbol / kind."""
    clauses: list[str] = []
    params: list = []
    if symbol is not None:
        clauses.append("symbol = ?")
        params.append(symbol)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT * FROM events {where} ORDER BY ts DESC, id DESC LIMIT ?", params
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()
