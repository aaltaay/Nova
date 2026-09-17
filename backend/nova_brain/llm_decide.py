"""llm-decide pack: propose at L1 / Activate-off; fire only when live_fire_ready."""
from __future__ import annotations

import json
import logging
from typing import Any

from bot.llm_guard import estimate_usd, llm_configured
from constants_bot import (
    BOT_ACTION_KINDS,
    BOT_LLM_MIN_INTERVAL_SEC,
    BOT_LLM_USD_PER_CALL_EST,
    BOT_PACK_LLM_DECIDE,
)
from nova_brain import llm_http

logger = logging.getLogger("nova_brain")

_SYSTEM = (
    "You are Nova's llm-decide pack. Reply with JSON only: "
    '{"proposals":[{"symbol":"TICK","side":"BUY|SELL","kind":"allowlisted",'
    '"reason":"short","confidence":0.0}]}. Never send qty or shares. '
    "Only listed symbols and kinds. Empty proposals is allowed."
)


def _load_json(raw: str) -> Any:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:].lstrip()
    try:
        return json.loads(text)
    except ValueError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                return None
        return None


def parse_proposals(
    raw: str,
    eligible: set[str],
    kinds: set[str],
) -> list[dict[str, Any]]:
    data = _load_json(raw)
    if not isinstance(data, dict):
        return []
    rows = data.get("proposals")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed = kinds or set(BOT_ACTION_KINDS)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("qty") is not None or row.get("shares") is not None:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        side = str(row.get("side") or "").strip().upper()
        kind = str(row.get("kind") or row.get("action") or "").strip()
        reason = str(row.get("reason") or "").strip()
        if symbol in seen or symbol not in eligible:
            continue
        if side not in ("BUY", "SELL") or kind not in allowed or not reason:
            continue
        confidence = row.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None
            if confidence is not None and (confidence < 0 or confidence > 1):
                confidence = None
        seen.add(symbol)
        out.append(
            {
                "symbol": symbol,
                "side": side,
                "kind": kind,
                "reason": reason[:280],
                "confidence": confidence,
            }
        )
    return out


def _interval(session: dict[str, Any]) -> float:
    settings = dict(session.get("pack_settings") or {}).get(BOT_PACK_LLM_DECIDE) or {}
    try:
        return max(1.0, float(settings.get("min_interval_sec") or BOT_LLM_MIN_INTERVAL_SEC))
    except (TypeError, ValueError):
        return float(BOT_LLM_MIN_INTERVAL_SEC)


def _context(session: dict[str, Any], watch: dict[str, Any]) -> str:
    caps = dict(session.get("caps") or {})
    symbols = []
    for row in watch.get("symbols") or []:
        symbols.append(
            {
                "symbol": row.get("symbol"),
                "last": row.get("last"),
                "halted": bool(row.get("halted")),
                "position_qty": row.get("position_qty"),
            }
        )
    payload = {
        "level": session.get("level"),
        "armed": bool(session.get("armed")),
        "live_fire_ready": bool(session.get("live_fire_ready")),
        "kinds": list(caps.get("allowlist") or BOT_ACTION_KINDS),
        "max_shares": caps.get("max_shares") or 1,
        "eligible": list(watch.get("eligible") or []),
        "symbols": symbols,
    }
    return json.dumps(payload, separators=(",", ":"))


def tick(
    client: Any,
    *,
    session: dict[str, Any],
    now: float,
    last: dict[str, float],
    watch: dict[str, Any] | None = None,
) -> dict[str, float]:
    if str(session.get("active_pack") or "") != BOT_PACK_LLM_DECIDE:
        return last
    if now - float(last.get("ts") or 0) < _interval(session):
        return last
    if not llm_configured():
        return last
    snap = watch if watch is not None else client.watch()
    eligible = {
        str(name).strip().upper()
        for name in (snap.get("eligible") or [])
        if str(name).strip()
    }
    if not eligible:
        last["ts"] = now
        return last
    kinds = {
        str(kind)
        for kind in ((session.get("caps") or {}).get("allowlist") or BOT_ACTION_KINDS)
        if kind in BOT_ACTION_KINDS
    }
    try:
        client.charge_llm(float(BOT_LLM_USD_PER_CALL_EST))
        result = llm_http.chat(_SYSTEM, _context(session, snap))
    except Exception:
        logger.exception("nova-brain: llm-decide call failed")
        last["ts"] = now
        return last
    items = parse_proposals(str(result.get("content") or ""), eligible, kinds)
    fire_ok = bool(session.get("live_fire_ready"))
    for item in items:
        try:
            if fire_ok:
                client.fire(item["kind"], item["symbol"])
            else:
                client.propose(item)
        except Exception:
            logger.exception("nova-brain: llm-decide apply failed")
    _ = estimate_usd(result.get("usage") if isinstance(result, dict) else None)
    last["ts"] = now
    return last
