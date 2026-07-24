"""Bounded, provenance-preserving execution fill evidence."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from typing import Any

from constants import (
    EXECUTION_FILL_EVIDENCE_LIMIT,
    EXECUTION_METRICS_QUERY_LIMIT,
)

PROVENANCES = frozenset({"execDetails", "orderStatus", "reconciliation_poll"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_fill_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    order_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    provenance TEXT NOT NULL,
    fill_state TEXT NOT NULL,
    exchange_ts_utc TEXT,
    callback_wall_ns INTEGER NOT NULL,
    callback_perf_ns INTEGER NOT NULL,
    boot_id TEXT NOT NULL,
    price REAL,
    shares REAL,
    cumulative_shares REAL,
    remaining_qty REAL,
    average_fill_price REAL,
    requested_price REAL,
    reference_price REAL,
    leg_role TEXT NOT NULL,
    evidence_side TEXT,
    reference_source TEXT,
    aggregate_eligible INTEGER NOT NULL,
    slippage_per_share REAL,
    slippage_total REAL,
    slippage_bps REAL,
    slippage_excluded_reason TEXT,
    exchange_to_callback_ms REAL,
    exchange_delay_excluded_reason TEXT,
    broker_status TEXT,
    created_ts REAL NOT NULL,
    UNIQUE(execution_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_exec_fill_execution
ON execution_fill_evidence(execution_id, sequence);
"""


def init_db(conn=None) -> None:
    from execution import store

    owned = conn is None
    db = conn or store.get_connection()
    try:
        db.executescript(_SCHEMA)
        columns = {
            str(row["name"])
            for row in db.execute(
                "PRAGMA table_info(execution_fill_evidence)"
            ).fetchall()
        }
        migrations = {
            "leg_role": "TEXT",
            "evidence_side": "TEXT",
            "reference_source": "TEXT",
            "aggregate_eligible": "INTEGER NOT NULL DEFAULT 0",
            "slippage_excluded_reason": "TEXT",
        }
        migrated = False
        for name, sql_type in migrations.items():
            if name not in columns:
                db.execute(
                    f"ALTER TABLE execution_fill_evidence "
                    f"ADD COLUMN {name} {sql_type}"
                )
                migrated = True
        if migrated:
            db.execute(
                """
                UPDATE execution_fill_evidence
                SET leg_role = COALESCE(leg_role, 'legacy_unknown'),
                    aggregate_eligible = 0,
                    slippage_per_share = NULL,
                    slippage_total = NULL,
                    slippage_bps = NULL,
                    slippage_excluded_reason = 'legacy_leg_attribution_unknown'
                """
            )
        db.commit()
    finally:
        if owned:
            db.close()


def merge_execution_payload(execution_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge safe measurement metadata without replacing command payload."""
    from execution import store

    conn = store.get_connection()
    try:
        row = conn.execute(
            "SELECT payload_json FROM executions WHERE id = ?", (execution_id,)
        ).fetchone()
        if row is None:
            return {}
        payload = json.loads(row["payload_json"] or "{}")
        payload.update(patch)
        conn.execute(
            "UPDATE executions SET payload_json = ?, updated_ts = ? WHERE id = ?",
            (json.dumps(payload), time.time(), execution_id),
        )
        conn.commit()
        return payload
    finally:
        conn.close()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _exchange_time(value: Any) -> tuple[str | None, int | None, str | None]:
    if value is None:
        return None, None, "exchange_timestamp_missing"
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None, None, "exchange_timestamp_invalid"
    if parsed is None:
        return None, None, "exchange_timestamp_invalid"
    if parsed.tzinfo is None:
        return parsed.isoformat(), None, "exchange_timestamp_timezone_unknown"
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat().replace("+00:00", "Z"), int(utc.timestamp() * 1e9), None


def _slippage(
    side: str | None,
    average_fill: float | None,
    reference: float | None,
    cumulative_shares: float | None,
) -> tuple[float | None, float | None, float | None]:
    normalized_side = str(side or "").upper()
    if (
        normalized_side not in ("BUY", "SELL")
        or average_fill is None
        or reference is None
        or reference <= 0
    ):
        return None, None, None
    direction = 1.0 if normalized_side == "BUY" else -1.0
    per_share = direction * (average_fill - reference)
    total = per_share * cumulative_shares if cumulative_shares is not None else None
    return per_share, total, per_share / reference * 10_000


def record_fill(
    *,
    execution_id: str,
    order_id: int,
    provenance: str,
    complete: bool,
    exchange_time: Any = None,
    callback_wall_ns: int | None = None,
    callback_perf_ns: int | None = None,
    price: Any = None,
    shares: Any = None,
    cumulative_shares: Any = None,
    remaining_qty: Any = None,
    average_fill_price: Any = None,
    broker_status: str | None = None,
    leg_role: str = "single",
    side: str | None = None,
    reference_price: Any = None,
    reference_source: str | None = None,
    aggregate_eligible: bool = True,
) -> bool:
    """Append one bounded callback/poll observation for a known execution."""
    from execution import store

    if provenance not in PROVENANCES:
        raise ValueError(f"unsupported fill provenance: {provenance}")
    init_db()
    callback_wall = int(callback_wall_ns or time.time_ns())
    callback_perf = int(callback_perf_ns or time.perf_counter_ns())
    conn = store.get_connection()
    try:
        execution = conn.execute(
            "SELECT payload_json, boot_id FROM executions WHERE id = ?",
            (execution_id,),
        ).fetchone()
        if execution is None or execution["boot_id"] != store.current_boot_id():
            return False
        count = int(conn.execute(
            "SELECT COUNT(*) FROM execution_fill_evidence WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()[0])
        if count >= EXECUTION_FILL_EVIDENCE_LIMIT:
            payload = json.loads(execution["payload_json"] or "{}")
            payload["fill_evidence_dropped_count"] = int(
                payload.get("fill_evidence_dropped_count") or 0
            ) + 1
            conn.execute(
                "UPDATE executions SET payload_json = ?, updated_ts = ? WHERE id = ?",
                (json.dumps(payload), time.time(), execution_id),
            )
            conn.commit()
            return False

        payload = json.loads(execution["payload_json"] or "{}")
        avg = _number(average_fill_price)
        fill_price = _number(price)
        if avg is None:
            avg = fill_price
        cumulative = _number(cumulative_shares)
        requested_qty = _number(payload.get("qty"))
        if cumulative is not None and requested_qty is not None and requested_qty > 0:
            complete = cumulative >= requested_qty
        actual_side = str(side or payload.get("side") or "").upper() or None
        reference = _number(reference_price)
        requested = _number(reference_price)
        if reference is None:
            reference = _number(payload.get("reference_price"))
        if requested is None:
            requested = _number(payload.get("requested_price"))
        if reference is None:
            reference = requested
        slippage_excluded = None
        if actual_side not in ("BUY", "SELL"):
            slippage_excluded = "side_unknown"
        elif reference is None or reference <= 0:
            slippage_excluded = "reference_price_unknown"
        slip_per_share, slip_total, slip_bps = _slippage(
            actual_side, avg, reference, cumulative,
        )
        exchange_iso, exchange_ns, excluded = _exchange_time(exchange_time)
        exchange_delay = None
        if exchange_ns is not None:
            if callback_wall >= exchange_ns:
                exchange_delay = (callback_wall - exchange_ns) / 1_000_000
            else:
                excluded = "negative_exchange_to_callback_wall_delta"

        conn.execute(
            """
            INSERT INTO execution_fill_evidence (
                execution_id, order_id, sequence, provenance, fill_state,
                exchange_ts_utc, callback_wall_ns, callback_perf_ns, boot_id,
                price, shares, cumulative_shares, remaining_qty,
                average_fill_price, requested_price, reference_price,
                leg_role, evidence_side, reference_source, aggregate_eligible,
                slippage_per_share, slippage_total, slippage_bps,
                slippage_excluded_reason,
                exchange_to_callback_ms, exchange_delay_excluded_reason,
                broker_status, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id, int(order_id), count + 1, provenance,
                "complete" if complete else "partial",
                exchange_iso, callback_wall, callback_perf, store.current_boot_id(),
                fill_price, _number(shares), cumulative, _number(remaining_qty),
                avg, requested, reference, str(leg_role or "unknown")[:32],
                actual_side, str(reference_source or "")[:64] or None,
                int(bool(aggregate_eligible)),
                slip_per_share, slip_total, slip_bps, slippage_excluded,
                exchange_delay, excluded, str(broker_status or "")[:64] or None,
                time.time(),
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def list_for_execution(execution_id: str) -> list[dict[str, Any]]:
    """Return bounded public evidence without broker/account identifiers."""
    from execution import store

    init_db()
    conn = store.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT sequence, provenance, fill_state, exchange_ts_utc,
                   callback_wall_ns, callback_perf_ns, price, shares,
                   cumulative_shares, remaining_qty, average_fill_price,
                   requested_price, reference_price, leg_role, evidence_side,
                   reference_source, aggregate_eligible, slippage_per_share,
                   slippage_total, slippage_bps, slippage_excluded_reason,
                   exchange_to_callback_ms,
                   exchange_delay_excluded_reason, broker_status
            FROM execution_fill_evidence
            WHERE execution_id = ?
            ORDER BY sequence ASC
            LIMIT ?
            """,
            (execution_id, EXECUTION_FILL_EVIDENCE_LIMIT),
        ).fetchall()
        result = [dict(row) for row in rows]
        for item in result:
            item["aggregate_eligible"] = bool(item["aggregate_eligible"])
        return result
    finally:
        conn.close()


def latency_rows(execution_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch bounded same-boot evidence for latency rollups."""
    from execution import store

    if not execution_ids:
        return []
    init_db()
    ids = execution_ids[:EXECUTION_METRICS_QUERY_LIMIT]
    marks = ",".join("?" for _ in ids)
    conn = store.get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT f.*, e.received_ns, e.broker_sent_ns, e.broker_ack_ns
            FROM execution_fill_evidence f
            JOIN executions e ON e.id = f.execution_id
            WHERE f.execution_id IN ({marks})
              AND f.boot_id = ? AND e.boot_id = ?
            ORDER BY f.created_ts DESC
            """,
            [*ids, store.current_boot_id(), store.current_boot_id()],
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
