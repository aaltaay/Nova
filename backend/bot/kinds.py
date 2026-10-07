"""NovaActionKind allowlist for L2 small-cap. Not hotkey row ids."""
from __future__ import annotations

from constants_bot import (
    BOT_ACTION_KINDS,
    BOT_BUY_KINDS,
    BOT_COVER_KINDS,
    BOT_ENTRY_KINDS,
    BOT_LATER_KINDS,
    BOT_SHORT_KINDS,
)

_ALL = frozenset(BOT_ACTION_KINDS)
_LATER = frozenset(BOT_LATER_KINDS)


def is_allowlisted(kind: str, enabled: list[str] | tuple[str, ...]) -> bool:
    return (kind or "").strip() in set(enabled) and kind in _ALL


def is_buy_kind(kind: str) -> bool:
    return (kind or "").strip() in BOT_BUY_KINDS


def is_short_kind(kind: str) -> bool:
    """A kind that opens or adds to a short (ADR 049, #778 step 5)."""
    return (kind or "").strip() in BOT_SHORT_KINDS


def is_cover_kind(kind: str) -> bool:
    return (kind or "").strip() in BOT_COVER_KINDS


def is_entry_kind(kind: str) -> bool:
    """A kind that opens a position, either side: the day's cap counts it and the day lock holds it."""
    return (kind or "").strip() in BOT_ENTRY_KINDS


def is_parked_later_kind(kind: str) -> bool:
    return (kind or "").strip() in _LATER


def normalize_kind(kind: str) -> str:
    return (kind or "").strip()


def default_allowlist() -> list[str]:
    return list(BOT_ACTION_KINDS)
