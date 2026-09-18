"""Per-order place-to-fill / place-to-terminal detective (#177).

On a terminal (or return-to-Working) state, append one JSONL row and a
structured ``IBKR_FILL_AUDIT`` log line. Quiet OK fills stay at DEBUG.
Warn / danger are loud so Nova Repo can ping.

Sample line::

    IBKR_FILL_AUDIT order_id=115728 symbol=SPCX side=BUY type=MKT mode=paper
    place_to_submit_ms=12 place_to_fill_ms=180 status=Filled level=ok

Owner: execution.fill_audit. Writes ``<NOVA_LOG_DIR>/fill-latency.jsonl``.
Invalidation: one row per order_id+status emission (caller de-dupes).
schema_version: 1.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from constants import (
    FILL_AUDIT_JSONL_FILENAME,
    FILL_AUDIT_MKT_RTH_DANGER_MS,
    FILL_AUDIT_MKT_RTH_WARN_MS,
    FILL_AUDIT_REASON_CLOCK_SKEW,
)
from execution import persist_queue
from execution.fill_audit_clock import (
    apply_fill_clock_guard,
    clock_guard_level,
    is_clock_skew_ms,
)
from paths import log_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_WORKING = frozenset({
    "PendingSubmit", "PreSubmitted", "Submitted", "ApiPending", "Working",
})

# In-memory last audit for Orders Today (#195). Owner: this module.
# Invalidation: process lifetime. Keyed by order_id and optional perm_id.
_STORE_BY_ORDER: dict[int, dict[str, Any]] = {}
_STORE_BY_PERM: dict[int, dict[str, Any]] = {}
_PLACED_BY_ORDER: dict[int, str] = {}
_PLACED_BY_PERM: dict[int, str] = {}


def reset_fill_audit_store_for_testing() -> None:
    """Test helper -- clear the process-lifetime audit join store."""
    _STORE_BY_ORDER.clear()
    _STORE_BY_PERM.clear()
    _PLACED_BY_ORDER.clear()
    _PLACED_BY_PERM.clear()


def remember_fill_audit(
    row: dict[str, Any],
    *,
    perm_id: int | None = None,
    nova_placed_at: str | None = None,
) -> None:
    """Keep the last detective row so the blotter can join without JSONL."""
    try:
        oid = int(row.get("order_id") or 0)
    except (TypeError, ValueError):
        oid = 0
    snapshot = dict(row)
    if oid > 0:
        _STORE_BY_ORDER[oid] = snapshot
        if nova_placed_at:
            _PLACED_BY_ORDER[oid] = nova_placed_at
    try:
        perm = int(perm_id or 0)
    except (TypeError, ValueError):
        perm = 0
    if perm > 0:
        _STORE_BY_PERM[perm] = snapshot
        if nova_placed_at:
            _PLACED_BY_PERM[perm] = nova_placed_at


def lookup_fill_audit(
    order_id: int | None,
    perm_id: int | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (stored classify row, nova_placed_at ISO) if remembered."""
    try:
        oid = int(order_id or 0)
    except (TypeError, ValueError):
        oid = 0
    try:
        perm = int(perm_id or 0)
    except (TypeError, ValueError):
        perm = 0
    if oid > 0 and oid in _STORE_BY_ORDER:
        return _STORE_BY_ORDER[oid], _PLACED_BY_ORDER.get(oid)
    if perm > 0 and perm in _STORE_BY_PERM:
        return _STORE_BY_PERM[perm], _PLACED_BY_PERM.get(perm)
    placed = _PLACED_BY_ORDER.get(oid) if oid > 0 else None
    if placed is None and perm > 0:
        placed = _PLACED_BY_PERM.get(perm)
    return None, placed

ClockIso = Callable[[], str]


def _parse_iso_ms(value: str | None) -> float | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp() * 1000.0


def _delta_ms(start_iso: str | None, end_iso: str | None) -> int | None:
    start = _parse_iso_ms(start_iso)
    end = _parse_iso_ms(end_iso)
    if start is None or end is None:
        return None
    return int(round(end - start))


def classify_fill_audit(
    *,
    order_id: int,
    symbol: str,
    side: str,
    order_type: str,
    mode: str,
    status: str,
    nova_placed_at: str | None,
    submitted_at: str | None,
    filled_at: str | None,
    terminal_at: str | None,
    has_fill: bool,
    rth: bool,
    status_history: tuple[str, ...] = (),
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Pure classifier -- fake clocks by passing ISO stamps."""
    typ = (order_type or "").upper()
    last = (status or "").strip()
    place_to_submit = _delta_ms(nova_placed_at, submitted_at)
    place_to_fill = _delta_ms(nova_placed_at, filled_at) if has_fill else None
    place_to_terminal = None
    if not has_fill:
        place_to_terminal = _delta_ms(nova_placed_at, terminal_at or now_iso)

    clock_reason = None
    if has_fill:
        place_to_fill, clock_reason = apply_fill_clock_guard(
            place_to_fill_ms=place_to_fill,
            place_to_submit_ms=place_to_submit,
            placed_iso=nova_placed_at,
            order_type=typ,
        )
    elif is_clock_skew_ms(place_to_terminal):
        clock_reason = FILL_AUDIT_REASON_CLOCK_SKEW

    returned = (
        any(s in {"Filled", "Inactive"} for s in status_history[:-1])
        and last in _WORKING
    )
    working_no_fill = (
        typ == "MKT"
        and rth
        and not has_fill
        and last in _WORKING
    )

    level = "ok"
    reason = "filled" if has_fill else "terminal"
    latency = place_to_fill if has_fill else place_to_terminal
    if clock_reason:
        level = clock_guard_level(clock_reason) or "ok"
        reason = clock_reason
    elif returned:
        level = "danger"
        reason = "return_to_working"
    elif working_no_fill:
        level = "danger"
        reason = "working_without_fill"
    elif typ == "MKT" and rth and latency is not None:
        if latency > FILL_AUDIT_MKT_RTH_DANGER_MS:
            level = "danger"
            reason = "mkt_rth_slow"
        elif latency > FILL_AUDIT_MKT_RTH_WARN_MS:
            level = "warn"
            reason = "mkt_rth_slow"

    row = {
        "schema_version": SCHEMA_VERSION,
        "order_id": int(order_id),
        "symbol": (symbol or "").upper(),
        "side": (side or "").upper(),
        "type": typ,
        "mode": mode,
        "place_to_submit_ms": place_to_submit,
        "status": last,
        "level": level,
        "reason": reason,
    }
    if has_fill:
        row["place_to_fill_ms"] = place_to_fill
    else:
        row["place_to_terminal_ms"] = place_to_terminal
    return row


def fill_audit_path() -> Path:
    return log_dir() / FILL_AUDIT_JSONL_FILENAME


def emit_fill_audit(row: dict[str, Any]) -> None:
    """Append JSONL + structured log. Caller owns de-dupe."""
    remember_fill_audit(row)
    line = json.dumps(row, separators=(",", ":"), sort_keys=True)
    path = fill_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    parts = (
        f"IBKR_FILL_AUDIT order_id={row.get('order_id')} "
        f"symbol={row.get('symbol')} side={row.get('side')} "
        f"type={row.get('type')} mode={row.get('mode')} "
        f"place_to_submit_ms={row.get('place_to_submit_ms')} "
        f"status={row.get('status')} level={row.get('level')}"
    )
    if "place_to_fill_ms" in row:
        parts += f" place_to_fill_ms={row.get('place_to_fill_ms')}"
    else:
        parts += f" place_to_terminal_ms={row.get('place_to_terminal_ms')}"
    level = str(row.get("level") or "ok")
    if level == "danger":
        logger.error("%s", parts)
    elif level == "warn":
        logger.warning("%s", parts)
    else:
        logger.debug("%s", parts)


def _iso_from_unix(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def audit_place_watch(watch: Any, cmd: Any, mode: str, status: str | None) -> None:
    """Emit one detective row after place ack / reject. Safe off the IB loop."""
    if watch is None:
        return
    symbol = ""
    side = ""
    order_type = "MKT"
    outside_rth = False
    if cmd is not None:
        try:
            symbol = str(cmd.normalized_symbol() or "")
        except Exception:
            symbol = str(getattr(cmd, "symbol", "") or "")
        side = str(getattr(cmd, "side", "") or "")
        order_type = str(getattr(cmd, "order_type", None) or "MKT")
        outside_rth = bool(getattr(cmd, "outside_rth", False))
    queue_watch_fill_audit(
        watch,
        symbol=symbol,
        side=side,
        order_type=order_type,
        mode=mode,
        status=status or "",
        outside_rth=outside_rth,
    )


def queue_watch_fill_audit(
    watch: Any,
    *,
    symbol: str,
    side: str,
    order_type: str,
    mode: str,
    status: str,
    outside_rth: bool = False,
    nova_placed_at: str | None = None,
) -> None:
    if watch is None or getattr(watch, "_fill_audit_emitted", False):
        return
    watch._fill_audit_emitted = True
    oid = int(getattr(watch, "order_id", 0) or 0)
    history = tuple(getattr(watch, "_status_history", ()) or ())
    has_fill = bool(getattr(watch, "fills", None))
    execution_id = getattr(watch, "execution_id", None)

    def _write() -> None:
        placed = nova_placed_at
        typ = order_type or "MKT"
        if execution_id:
            try:
                from execution import store

                row = store.get_by_id(execution_id)
            except Exception:
                logger.exception("fill_audit: ledger read failed for %s", execution_id)
                row = None
            if row:
                payload = row.get("payload") or {}
                if not placed:
                    placed = str(payload.get("nova_placed_at") or "").strip() or None
                if not placed and row.get("created_ts"):
                    placed = _iso_from_unix(float(row["created_ts"]))
                typ = str(payload.get("order_type") or typ or "MKT")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        row = classify_fill_audit(
            order_id=oid,
            symbol=symbol,
            side=side,
            order_type=typ,
            mode=mode,
            status=status or "",
            nova_placed_at=placed,
            submitted_at=None,
            filled_at=now if has_fill else None,
            terminal_at=None if has_fill else now,
            has_fill=has_fill,
            rth=not outside_rth,
            status_history=history,
            now_iso=now,
        )
        remember_fill_audit(
            row,
            perm_id=getattr(watch, "perm_id", None),
            nova_placed_at=placed,
        )
        emit_fill_audit(row)

    persist_queue.submit(f"fill audit {oid}", _write)
