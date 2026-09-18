"""One-active L2 pack catalog. Risk sleeve stays small-cap."""
from __future__ import annotations

from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_PACK_DEFAULT,
    BOT_PACK_DESCRIPTIONS,
    BOT_PACK_HALT_LULD,
    BOT_PACK_LABELS,
    BOT_PACK_LLM_DECIDE,
    BOT_PACK_QUOTE_SPIKE,
    BOT_PACK_STUBS,
    BOT_PACK_VOLUME,
    BOT_PACKS,
    BOT_QUOTE_SPIKE_COOLDOWN_SEC,
    BOT_QUOTE_SPIKE_MIN_PCT,
    BOT_QUOTE_SPIKE_WINDOW_SEC,
    BOT_REASON_PACK_STUB,
    BOT_VOLUME_BASELINE_SEC,
    BOT_VOLUME_COOLDOWN_SEC,
    BOT_VOLUME_MIN_MULT,
    BOT_VOLUME_WINDOW_SEC,
)


def pack_status(pack_id: str) -> str:
    if pack_id in BOT_PACK_STUBS:
        return "stub"
    return "live"


def catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pack_id in BOT_PACKS:
        rows.append(
            {
                "id": pack_id,
                "label": BOT_PACK_LABELS[pack_id],
                "status": pack_status(pack_id),
                "description": BOT_PACK_DESCRIPTIONS[pack_id],
            }
        )
    return rows


def normalize_pack(name: str | None) -> str:
    pack = (name or "").strip() or BOT_PACK_DEFAULT
    if pack not in BOT_PACKS:
        raise BotError(
            f"unknown pack {pack!r} -- day-one live pack is {BOT_PACK_HALT_LULD}",
            400,
        )
    return pack


def default_pack_settings() -> dict[str, Any]:
    return {
        BOT_PACK_HALT_LULD: {
            "resume_kind": "buy_market",
            "cooldown_sec": 30,
        },
        BOT_PACK_QUOTE_SPIKE: {
            "spike_kind": "buy_market",
            "min_pct": BOT_QUOTE_SPIKE_MIN_PCT,
            "window_sec": BOT_QUOTE_SPIKE_WINDOW_SEC,
            "cooldown_sec": BOT_QUOTE_SPIKE_COOLDOWN_SEC,
        },
        BOT_PACK_VOLUME: {
            "enabled": True,
            "volume_kind": "buy_market",
            "min_mult": BOT_VOLUME_MIN_MULT,
            "window_sec": BOT_VOLUME_WINDOW_SEC,
            "baseline_sec": BOT_VOLUME_BASELINE_SEC,
            "cooldown_sec": BOT_VOLUME_COOLDOWN_SEC,
        },
        BOT_PACK_LLM_DECIDE: {
            "min_interval_sec": 15,
            "note": "Live fire needs L2 + Activate -- no hidden arm flag",
        },
    }


def merge_pack_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-merge session pack settings onto defaults.

    A leftover quote-spike or volume stub blob (no signal keys) is replaced,
    not shallow-kept. Other packs keep operator overrides.
    """
    defaults = default_pack_settings()
    incoming = dict(raw or {})
    out: dict[str, Any] = {}
    for pack_id, base in defaults.items():
        extra = incoming.get(pack_id)
        if not isinstance(extra, dict):
            out[pack_id] = dict(base)
            continue
        if pack_id == BOT_PACK_QUOTE_SPIKE and "spike_kind" not in extra and "min_pct" not in extra:
            out[pack_id] = dict(base)
            continue
        if pack_id == BOT_PACK_VOLUME and "min_mult" not in extra and "window_sec" not in extra:
            out[pack_id] = dict(base)
            continue
        out[pack_id] = {**base, **extra}
    for pack_id, extra in incoming.items():
        if pack_id not in out:
            out[pack_id] = extra
    return out


def assert_pack_can_fire(pack: str) -> None:
    if pack in BOT_PACK_STUBS:
        raise BotError(
            f"pack {pack} is a stub and cannot fire",
            409,
            BOT_REASON_PACK_STUB,
        )
