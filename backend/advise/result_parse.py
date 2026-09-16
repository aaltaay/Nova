"""Parse the risk-judge JSON into a card + ticket prefill (no order send)."""
from __future__ import annotations

import json
import re
from typing import Any

from constants_advise import ADVISE_TICKET_DEFAULT_QTY

_STANCES = {"LONG", "SHORT", "HOLD"}


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out = [str(item).strip() for item in value if str(item).strip()]
    return out[:8]


def ticket_for_stance(symbol: str, stance: str, qty_hint: int | None) -> dict[str, Any] | None:
    if stance == "HOLD":
        return None
    side = "BUY" if stance == "LONG" else "SELL"
    qty = qty_hint if qty_hint and qty_hint > 0 else ADVISE_TICKET_DEFAULT_QTY
    return {
        "symbol": symbol,
        "side": side,
        "order_type": "MKT",
        "quantity_value": str(qty),
        "limit_price": "",
        "places": False,
    }


def parse_judge(symbol: str, text: str) -> dict[str, Any]:
    obj = _extract_json(text) or {}
    stance = str(obj.get("stance") or "HOLD").strip().upper()
    if stance not in _STANCES:
        stance = "HOLD"
    qty_hint = None
    raw_qty = obj.get("qty_hint")
    try:
        if raw_qty is not None:
            qty_hint = int(raw_qty)
    except (TypeError, ValueError):
        qty_hint = None
    reasons = _strings(obj.get("reasons"))
    risks = _strings(obj.get("risks"))
    if not reasons:
        reasons = ["Judge did not return structured reasons -- see transcript."]
    if not risks:
        risks = ["Judge did not return structured risks -- see transcript."]
    return {
        "stance": stance,
        "reasons": reasons,
        "risks": risks,
        "ticket": ticket_for_stance(symbol, stance, qty_hint),
    }
