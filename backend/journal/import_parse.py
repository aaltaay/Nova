"""Parse operator-uploaded journal files for Reports import.

Never invents P/L or commissions. A row missing a required fact is skipped.
Owner: journal.import_parse. Invalidation: none (pure). schema_version: n/a.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from constants import (
    JOURNAL_IBKR_IMPORT_MAX_ROWS,
    JOURNAL_IMPORT_ACCEPTED_SUFFIXES,
    JOURNAL_IMPORT_MAX_BYTES,
    JOURNAL_TAGS_MAX_PER_TRADE,
)

_ET = ZoneInfo("America/New_York")
_RTH_CLOSE = time(16, 0)

REQUIRED_FIELDS = (
    "symbol",
    "side",
    "qty",
    "entry_price",
    "exit_price",
    "pnl",
    "closed_ts",
)

_HEADER_ALIASES = {
    "ticker": "symbol",
    "quantity": "qty",
    "shares": "qty",
    "entry": "entry_price",
    "entryprice": "entry_price",
    "exit": "exit_price",
    "exitprice": "exit_price",
    "net_pnl": "pnl",
    "netpnl": "pnl",
    "profit": "pnl",
    "pl": "pnl",
    "closed": "closed_at",
    "date": "closed_at",
    "exit_time": "closed_at",
    "exit_date": "closed_at",
    "closedate": "closed_at",
    "opened": "opened_at",
    "entry_time": "opened_at",
    "entry_date": "opened_at",
    "stop": "stop_price",
    "target": "target_price",
    "comm": "commission",
    "fees": "commission",
    "note": "notes",
}

_SIDES = {"long", "short"}


def _norm_header(raw: str) -> str:
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    return _HEADER_ALIASES.get(key, key)


def parse_timestamp(value: Any) -> float | None:
    """Unix seconds, millis, ISO datetime, or YYYY-MM-DD (that ET session day)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1e12:
            number /= 1000.0
        return number
    text = str(value).strip()
    if not text:
        return None
    try:
        return parse_timestamp(float(text))
    except ValueError:
        pass
    if len(text) >= 10 and text[4] == "-" and text[7] == "-" and text[10:11] in ("", " "):
        if len(text) == 10:
            day = date.fromisoformat(text)
            stamp = datetime.combine(day, _RTH_CLOSE, tzinfo=_ET)
            return stamp.timestamp()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_ET)
    return parsed.timestamp()


def _finite_float(value: Any, *, required: bool) -> float | None:
    if value is None or value == "":
        if required:
            raise ValueError("missing")
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("not a finite number")
    return number


def _normalize_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        parts = [str(item).strip() for item in raw]
    else:
        text = str(raw).strip()
        if not text:
            return []
        splitter = ";" if ";" in text else ("|" if "|" in text else ",")
        parts = [part.strip() for part in text.split(splitter)]
    return [part for part in parts if part][:JOURNAL_TAGS_MAX_PER_TRADE]


def _lookup(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def normalize_trade_row(row: dict[str, Any], index: int) -> tuple[dict[str, Any] | None, str | None]:
    """Return (trade, None) or (None, skip reason). Never computes pnl."""
    mapped = {_norm_header(key): value for key, value in row.items()}
    try:
        symbol = str(_lookup(mapped, "symbol") or "").strip().upper()
        if not symbol:
            return None, f"row {index}: missing symbol"
        side = str(_lookup(mapped, "side") or "").strip().lower()
        if side not in _SIDES:
            return None, f"row {index}: side must be long or short (not invented)"
        qty_raw = _lookup(mapped, "qty")
        if qty_raw is None:
            return None, f"row {index}: missing qty"
        qty = int(float(qty_raw))
        if qty <= 0:
            return None, f"row {index}: qty must be > 0"
        entry = _finite_float(_lookup(mapped, "entry_price"), required=True)
        exit_price = _finite_float(_lookup(mapped, "exit_price"), required=True)
        pnl = _finite_float(_lookup(mapped, "pnl"), required=True)
        closed_ts = parse_timestamp(_lookup(mapped, "closed_ts", "closed_at"))
        if closed_ts is None:
            return None, f"row {index}: missing closed_ts/closed_at"
        opened_ts = parse_timestamp(_lookup(mapped, "opened_ts", "opened_at"))
        if opened_ts is None:
            opened_ts = closed_ts
        commission_raw = _lookup(mapped, "commission")
        commission = None
        if commission_raw is not None:
            commission = _finite_float(commission_raw, required=False)
        stop = _finite_float(_lookup(mapped, "stop_price"), required=False)
        target = _finite_float(_lookup(mapped, "target_price"), required=False)
    except (TypeError, ValueError) as exc:
        return None, f"row {index}: {exc}"

    setup = _lookup(mapped, "setup")
    notes = str(_lookup(mapped, "notes") or "")
    return {
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "entry_price": entry,
        "exit_price": exit_price,
        "pnl": pnl,
        "closed_ts": closed_ts,
        "opened_ts": opened_ts,
        "commission": commission,
        "stop_price": stop,
        "target_price": target,
        "setup": None if setup is None else str(setup),
        "notes": notes,
        "tags": _normalize_tags(_lookup(mapped, "tags")),
    }, None


def detect_format(filename: str, text: str) -> str:
    lower = (filename or "").lower()
    for suffix in JOURNAL_IMPORT_ACCEPTED_SUFFIXES:
        if lower.endswith(suffix):
            return suffix[1:]
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if stripped.startswith("<"):
        raise ValueError(
            "XML/Flex is not wired -- upload CSV or JSON with explicit pnl facts."
        )
    return "csv"


def _rows_from_json(text: str) -> list[dict[str, Any]]:
    payload = json.loads(text)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("trades"), list):
        rows = payload["trades"]
    else:
        raise ValueError('JSON must be an array or {"trades": [...]}')
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("JSON trades must be objects")
    return rows


def _rows_from_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV is missing a header row")
    return [dict(row) for row in reader]


def parse_import_bytes(filename: str, raw: bytes) -> dict[str, Any]:
    if len(raw) > JOURNAL_IMPORT_MAX_BYTES:
        return {
            "ok": False,
            "error": f"File too large (max {JOURNAL_IMPORT_MAX_BYTES} bytes).",
            "trades": [],
            "skipped": [],
            "source": None,
        }
    text = raw.decode("utf-8-sig")
    if not text.strip():
        return {
            "ok": False,
            "error": "File is empty.",
            "trades": [],
            "skipped": [],
            "source": None,
        }
    try:
        source = detect_format(filename, text)
        rows = _rows_from_json(text) if source == "json" else _rows_from_csv(text)
    except (ValueError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "trades": [],
            "skipped": [],
            "source": None,
        }
    if not rows:
        return {
            "ok": False,
            "error": "No trade rows in file.",
            "trades": [],
            "skipped": [],
            "source": source,
        }
    if len(rows) > JOURNAL_IBKR_IMPORT_MAX_ROWS:
        return {
            "ok": False,
            "error": f"Too many rows (max {JOURNAL_IBKR_IMPORT_MAX_ROWS}).",
            "trades": [],
            "skipped": [],
            "source": source,
        }
    trades: list[dict[str, Any]] = []
    skipped: list[str] = []
    for index, row in enumerate(rows):
        trade, reason = normalize_trade_row(row, index)
        if trade is None:
            skipped.append(reason or f"row {index}: skipped")
            continue
        trades.append(trade)
    if not trades:
        return {
            "ok": False,
            "error": "No valid trades -- every row lacked a required fact.",
            "trades": [],
            "skipped": skipped,
            "source": source,
        }
    return {
        "ok": True,
        "error": None,
        "trades": trades,
        "skipped": skipped,
        "source": source,
    }
