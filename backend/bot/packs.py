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
    BOT_PACK_STUBS,
    BOT_PACKS,
    BOT_REASON_PACK_STUB,
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
        "quote-spike": {"enabled": False, "note": "stub -- no signal logic yet"},
        "volume": {"enabled": False, "note": "stub -- no signal logic yet"},
        BOT_PACK_LLM_DECIDE: {
            "min_interval_sec": 15,
            "note": "Live fire needs L2 + Activate -- no hidden arm flag",
        },
    }


def assert_pack_can_fire(pack: str) -> None:
    if pack in BOT_PACK_STUBS:
        raise BotError(
            f"pack {pack} is a stub and cannot fire",
            409,
            BOT_REASON_PACK_STUB,
        )
