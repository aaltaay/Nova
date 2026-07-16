"""
Best-effort IBKR fill import into the journal.

Never fabricates fills. When Gateway is disconnected, callers must supply a
JSON trade list or receive a loud error.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants import JOURNAL_IBKR_IMPORT_MAX_ROWS, JOURNAL_TAGS_MAX_PER_TRADE
from journal.store import record_trade

logger = logging.getLogger(__name__)


def _normalize_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    tags = [str(t).strip() for t in raw if str(t).strip()]
    return tags[:JOURNAL_TAGS_MAX_PER_TRADE]


def import_trades_from_json(rows: list[dict]) -> dict[str, Any]:
    """Insert journal trades from an explicit JSON list."""
    if not rows:
        return {
            "ok": False,
            "source": "json",
            "error": "No trades provided — upload a JSON array of trade objects.",
            "imported": 0,
        }
    if len(rows) > JOURNAL_IBKR_IMPORT_MAX_ROWS:
        return {
            "ok": False,
            "source": "json",
            "error": f"Too many rows (max {JOURNAL_IBKR_IMPORT_MAX_ROWS}).",
            "imported": 0,
        }

    imported = 0
    errors: list[str] = []
    now = time.time()

    for idx, row in enumerate(rows):
        try:
            symbol = str(row["symbol"]).upper()
            side = str(row.get("side", "long")).lower()
            qty = int(row["qty"])
            entry = float(row["entry_price"])
            exit_price = float(row["exit_price"]) if row.get("exit_price") is not None else None
            stop = float(row["stop_price"]) if row.get("stop_price") is not None else None
            target = float(row["target_price"]) if row.get("target_price") is not None else None
            pnl = float(row["pnl"]) if row.get("pnl") is not None else None
            setup = row.get("setup")
            notes = str(row.get("notes", ""))
            tags = _normalize_tags(row.get("tags"))
            opened_ts = float(row["opened_ts"]) if row.get("opened_ts") is not None else now
            closed_ts = float(row["closed_ts"]) if row.get("closed_ts") is not None else now
            adherent = row.get("adherent")

            record_trade(
                symbol=symbol,
                setup=setup,
                side=side,
                qty=qty,
                entry_price=entry,
                stop_price=stop,
                target_price=target,
                exit_price=exit_price,
                pnl=pnl,
                adherent=adherent,
                opened_ts=opened_ts,
                closed_ts=closed_ts,
                notes=notes,
                tags=tags,
                is_mock=False,
            )
            imported += 1
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"row {idx}: {exc}")

    return {
        "ok": imported > 0,
        "source": "json",
        "imported": imported,
        "errors": errors,
        "error": None if imported else "No valid trades imported.",
    }


def try_import_from_ibkr_gateway() -> dict[str, Any]:
    """Read fills from IB Gateway when connected; does not invent data."""
    try:
        from ibkr import client as _client
    except ImportError:
        return {
            "ok": False,
            "source": "ibkr",
            "error": "IBKR module unavailable.",
            "imported": 0,
        }

    ib = _client.get_ib()
    if ib is None:
        return {
            "ok": False,
            "source": "ibkr",
            "error": "IB Gateway not connected — log in to Gateway or upload a JSON trade list.",
            "imported": 0,
            "requires_gateway": True,
        }

    try:
        fills = list(ib.fills())
    except Exception as exc:
        logger.warning("IBKR fills() failed: %s", exc)
        return {
            "ok": False,
            "source": "ibkr",
            "error": f"IBKR fills unavailable: {exc}",
            "imported": 0,
            "requires_gateway": True,
        }

    if not fills:
        return {
            "ok": False,
            "source": "ibkr",
            "error": "IB Gateway connected but returned zero fills — upload JSON trades or execute paper fills first.",
            "imported": 0,
            "fill_count": 0,
        }

    # Best-effort: expose raw fill count; round-trip reconstruction needs explicit JSON.
    return {
        "ok": False,
        "source": "ibkr",
        "error": (
            f"Gateway returned {len(fills)} fill(s) but round-trip import is not automated yet — "
            "upload a JSON trade list via this endpoint."
        ),
        "imported": 0,
        "fill_count": len(fills),
        "requires_json": True,
    }
