"""Compact Sensor Board snapshots for the llm-decide prompt."""
from __future__ import annotations

from typing import Any

from constants_bot import BOT_ACTION_KINDS, BOT_LLM_QTY_PRESETS

_LIST_TAIL = 3
_MAP_KEYS = 24
_STR_CAP = 160
_DEPTH = 3


def bound_value(value: Any, *, depth: int = 0) -> Any:
    if depth > _DEPTH:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in list(value.keys())[:_MAP_KEYS]:
            out[str(key)] = bound_value(value.get(key), depth=depth + 1)
        return out
    if isinstance(value, list):
        return [bound_value(item, depth=depth + 1) for item in value[-_LIST_TAIL:]]
    if isinstance(value, str):
        return value[:_STR_CAP]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:80]


def compact_snapshot(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    rows = payload.get("sensors") if isinstance(payload.get("sensors"), list) else []
    compact_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {
            "sensor": row.get("sensor"),
            "status": row.get("status"),
            "as_of": row.get("as_of"),
            "data": bound_value(row.get("data")),
        }
        error = row.get("error")
        if error:
            item["error"] = str(error)[:_STR_CAP]
        compact_rows.append(item)
    return {
        "symbol": payload.get("symbol"),
        "count": len(compact_rows),
        "sensors": compact_rows,
    }


def build_user_payload(
    session: dict[str, Any],
    watch: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    caps = dict(session.get("caps") or {})
    symbols = []
    for row in watch.get("symbols") or []:
        if not isinstance(row, dict):
            continue
        symbols.append(
            {
                "symbol": row.get("symbol"),
                "last": row.get("last"),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "halted": bool(row.get("halted")),
                "position_qty": row.get("position_qty"),
            }
        )
    sensors = {
        str(symbol).strip().upper(): compact_snapshot(snap)
        for symbol, snap in snapshots.items()
        if str(symbol).strip()
    }
    return {
        "level": session.get("level"),
        "armed": bool(session.get("armed")),
        "live_fire_ready": bool(session.get("live_fire_ready")),
        "kinds": list(caps.get("allowlist") or BOT_ACTION_KINDS),
        "max_shares": caps.get("max_shares") or 1,
        "qty_preset": BOT_LLM_QTY_PRESETS[0],
        "eligible": list(watch.get("eligible") or []),
        "symbols": symbols,
        "sensors": sensors,
    }
