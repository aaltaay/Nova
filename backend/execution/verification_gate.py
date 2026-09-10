"""Session latch for IBKR Client Portal verification-required rejects."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from constants import (
    IBKR_VERIFICATION_REQUIRED_MARKERS,
    IBKR_VERIFICATION_REQUIRED_REASON,
)
from execution.models import ExecutionCommand
from ibkr import account as _account
from ibkr.errors import IbkrAccountError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RejectDetail:
    message: str
    reason_code: str


_blocked_symbols: set[str] = set()


def _symbol(value: str | None) -> str:
    return (value or "").strip().upper()


def _message(symbol: str) -> str:
    suffix = f" {symbol}" if symbol else ""
    return (
        "Order was not placed. IBKR requires Client Portal verification "
        f"before accepting a new{suffix} order."
    )


def latch(symbol: str | None) -> None:
    normalized = _symbol(symbol)
    if normalized and normalized not in _blocked_symbols:
        _blocked_symbols.add(normalized)
        logger.warning(
            "execution verification: blocked new entries for symbol=%s",
            normalized,
        )


def blocked_symbols() -> tuple[str, ...]:
    return tuple(sorted(_blocked_symbols))


def acknowledge(symbol: str | None) -> bool:
    """Clear one symbol only after explicit operator verification."""
    normalized = _symbol(symbol)
    was_blocked = normalized in _blocked_symbols
    _blocked_symbols.discard(normalized)
    if was_blocked:
        logger.info(
            "execution verification: operator acknowledged symbol=%s",
            normalized,
        )
    return was_blocked


def classify_reject(
    error_code: int | None,
    error_message: str | None,
    symbol: str | None,
) -> RejectDetail | None:
    """Type and latch the exact IBKR token-verification rejection."""
    text = str(error_message or "").upper()
    if int(error_code or 0) != 201:
        return None
    if not all(marker in text for marker in IBKR_VERIFICATION_REQUIRED_MARKERS):
        return None
    normalized = _symbol(symbol)
    latch(normalized)
    return RejectDetail(
        message=_message(normalized),
        reason_code=IBKR_VERIFICATION_REQUIRED_REASON,
    )


def _is_risk_increasing_entry(cmd: ExecutionCommand) -> bool:
    if cmd.operation not in ("place", "bracket"):
        return False
    if cmd.source in ("flatten", "kill", "cancel_working"):
        return False
    if cmd.operation == "bracket" or cmd.short_entry:
        return True
    if (cmd.side or "").upper() == "SELL":
        # Non-short SELL is position-reducing after validate.check_account_and_position.
        return False
    if (cmd.side or "").upper() != "BUY":
        return True
    try:
        short_qty = _account.short_qty(cmd.normalized_symbol() or "")
    except IbkrAccountError:
        return True
    return float(cmd.qty or 0) > short_qty


def entry_block(cmd: ExecutionCommand) -> RejectDetail | None:
    """Block repeated entries while always allowing cancel/replace/exits."""
    symbol = _symbol(cmd.normalized_symbol())
    if symbol not in _blocked_symbols or not _is_risk_increasing_entry(cmd):
        return None
    return RejectDetail(
        message=(
            f"{_message(symbol)} Complete verification, then explicitly "
            "acknowledge it in Nova before retrying."
        ),
        reason_code=IBKR_VERIFICATION_REQUIRED_REASON,
    )


def reset_for_tests() -> None:
    _blocked_symbols.clear()
