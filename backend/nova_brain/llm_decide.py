"""llm-decide pack: propose at L1 / Activate-off; fire only when live_fire_ready."""
from __future__ import annotations

import json
import logging
from typing import Any

from bot.llm_guard import estimate_usd, llm_configured
from constants_bot import (
    BOT_ACTION_KINDS,
    BOT_LLM_MIN_INTERVAL_SEC,
    BOT_LLM_QTY_PRESETS,
    BOT_LLM_USD_PER_CALL_EST,
    BOT_PACK_LLM_DECIDE,
)
from nova_brain import llm_http
from nova_brain.sensors_context import build_user_payload

logger = logging.getLogger("nova_brain")

_SYSTEM = (
    "You are Nova's llm-decide pack on the brain socket. Reply with JSON only. "
    "Schema: {\"symbol\":\"TICK\",\"side\":\"BUY|SELL|HOLD\",\"kind\":\"allowlisted\","
    "\"qty_preset\":\"default\",\"reason\":\"short\",\"confidence\":0.0}. "
    "Or {\"proposals\":[<same>]}. Never send qty or shares. "
    "qty_preset must be default (session max_shares). "
    "HOLD or empty proposals means no action. Only listed symbols and kinds."
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


def _normalize_row(
    row: dict[str, Any],
    eligible: set[str],
    kinds: set[str],
    seen: set[str],
) -> dict[str, Any] | None:
    if row.get("qty") is not None or row.get("shares") is not None:
        return None
    symbol = str(row.get("symbol") or "").strip().upper()
    side = str(row.get("side") or "").strip().upper()
    kind = str(row.get("kind") or row.get("action") or "").strip()
    reason = str(row.get("reason") or "").strip()
    preset = str(row.get("qty_preset") or BOT_LLM_QTY_PRESETS[0]).strip().lower()
    if preset not in BOT_LLM_QTY_PRESETS:
        return None
    if side == "HOLD" or kind in ("", "none", "hold", "skip"):
        return None
    if symbol in seen or symbol not in eligible:
        return None
    if side not in ("BUY", "SELL") or kind not in kinds or not reason:
        return None
    confidence = row.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None and (confidence < 0 or confidence > 1):
            confidence = None
    seen.add(symbol)
    return {
        "symbol": symbol,
        "side": side,
        "kind": kind,
        "qty_preset": preset,
        "reason": reason[:280],
        "confidence": confidence,
    }


def parse_proposals(
    raw: str,
    eligible: set[str],
    kinds: set[str],
) -> list[dict[str, Any]] | None:
    data = _load_json(raw)
    if not isinstance(data, dict):
        return None
    allowed = kinds or set(BOT_ACTION_KINDS)
    seen: set[str] = set()
    rows: list[Any]
    if isinstance(data.get("proposals"), list):
        rows = data["proposals"]
    elif "symbol" in data or "kind" in data or "side" in data:
        rows = [data]
    else:
        return None
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = _normalize_row(row, eligible, allowed, seen)
        if item:
            out.append(item)
    return out


def _interval(session: dict[str, Any]) -> float:
    settings = dict(session.get("pack_settings") or {}).get(BOT_PACK_LLM_DECIDE) or {}
    try:
        return max(1.0, float(settings.get("min_interval_sec") or BOT_LLM_MIN_INTERVAL_SEC))
    except (TypeError, ValueError):
        return float(BOT_LLM_MIN_INTERVAL_SEC)


def _context(
    session: dict[str, Any],
    watch: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> str:
    return json.dumps(
        build_user_payload(session, watch, snapshots),
        separators=(",", ":"),
    )


def _load_snapshots(client: Any, eligible: set[str]) -> dict[str, dict[str, Any]] | None:
    snaps: dict[str, dict[str, Any]] = {}
    for symbol in eligible:
        try:
            snaps[symbol] = client.sensors_snapshot(symbol)
        except Exception:
            logger.exception(
                "nova-brain: sensor snapshot failed for %s -- no place",
                symbol,
            )
            return None
    return snaps


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
        logger.error(
            "nova-brain: llm-decide idle -- OPENROUTER_API_KEY or NOVA_LLM_API_KEY is required"
        )
        last["ts"] = now
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
    snapshots = _load_snapshots(client, eligible)
    if snapshots is None:
        last["ts"] = now
        return last
    try:
        client.charge_llm(float(BOT_LLM_USD_PER_CALL_EST))
        result = llm_http.chat(_SYSTEM, _context(session, snap, snapshots))
    except Exception:
        logger.exception("nova-brain: llm-decide call failed")
        last["ts"] = now
        return last
    items = parse_proposals(str(result.get("content") or ""), eligible, kinds)
    if items is None:
        logger.error("nova-brain: llm-decide rejected free-text / bad JSON -- no place")
        last["ts"] = now
        return last
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
