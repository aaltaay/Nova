"""Write parsed Reports-import trades into journal.db.

Never invents P/L. Optional commission is stored only when the file supplies it.
Owner: journal.import_apply. Invalidation: journal.db write. schema_version: n/a.
"""
from __future__ import annotations

import hashlib
from typing import Any

from journal.import_parse import parse_import_bytes
from journal.store import record_trade


def import_close_key(trade: dict[str, Any]) -> str:
    payload = "|".join(
        (
            str(trade["symbol"]),
            str(trade["side"]),
            str(trade["qty"]),
            f"{float(trade['entry_price']):.6f}",
            f"{float(trade['exit_price']):.6f}",
            f"{float(trade['pnl']):.6f}",
            f"{float(trade['closed_ts']):.3f}",
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"import:{digest}"


def apply_parsed_trades(trades: list[dict[str, Any]], *, source: str) -> dict[str, Any]:
    imported = 0
    duplicates = 0
    errors: list[str] = []
    for index, trade in enumerate(trades):
        trade_id = record_trade(
            symbol=trade["symbol"],
            setup=trade.get("setup"),
            side=trade["side"],
            qty=int(trade["qty"]),
            entry_price=float(trade["entry_price"]),
            stop_price=trade.get("stop_price"),
            target_price=trade.get("target_price"),
            exit_price=float(trade["exit_price"]),
            pnl=float(trade["pnl"]),
            adherent=None,
            opened_ts=float(trade["opened_ts"]),
            closed_ts=float(trade["closed_ts"]),
            notes=str(trade.get("notes") or ""),
            tags=list(trade.get("tags") or []),
            is_mock=False,
            close_key=import_close_key(trade),
            commission=trade.get("commission"),
        )
        if trade_id:
            imported += 1
        else:
            duplicates += 1
            errors.append(f"row {index}: duplicate close_key (already imported)")
    return {
        "ok": imported > 0,
        "source": source,
        "imported": imported,
        "duplicates": duplicates,
        "error": None if imported else "No new trades imported.",
        "errors": errors,
    }


def import_uploaded_file(filename: str, raw: bytes) -> dict[str, Any]:
    parsed = parse_import_bytes(filename, raw)
    if not parsed.get("ok"):
        return {
            "ok": False,
            "source": parsed.get("source"),
            "imported": 0,
            "duplicates": 0,
            "skipped": len(parsed.get("skipped") or []),
            "errors": list(parsed.get("skipped") or []),
            "error": parsed.get("error") or "Import failed.",
        }
    applied = apply_parsed_trades(parsed["trades"], source=str(parsed["source"]))
    applied["skipped"] = len(parsed.get("skipped") or [])
    applied["errors"] = list(parsed.get("skipped") or []) + list(applied.get("errors") or [])
    if not applied["ok"] and parsed.get("skipped"):
        applied["error"] = parsed.get("error") or applied.get("error")
    return applied
