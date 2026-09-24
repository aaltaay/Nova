"""Quote-apply helpers for scanner L1 (split from scanner_l1.py)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from constants import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
from ibkr import l1_minute as _l1_minute

logger = logging.getLogger(__name__)

ApplyQuoteFn = Callable[..., Optional[dict]]


def stamp_l1_minute(
    symbol: str,
    price: float,
    ts_unix: float,
    *,
    volume: int | None,
    last_size: float | None,
    quote_quality: str | None = None,
) -> None:
    if quote_quality == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK:
        # IBKR's prior close before the first trade is not a print: as a live
        # minute it drew wicks no exchange printed (APLX 2026-09-23 16:00 opened
        # at the 9.52 prior close while every trade was 8.55-8.71; #541).
        return
    try:
        _l1_minute.on_last(
            symbol,
            float(price),
            float(ts_unix),
            size=last_size,
            cum_volume=float(volume) if volume is not None else None,
        )
    except Exception:
        logger.debug("scanner_l1: l1_minute.on_last failed", exc_info=True)


def apply_quote_compat(
    apply_quote: ApplyQuoteFn,
    symbol: str,
    price: float,
    volume: int | None,
    prev_close: float | None,
    ts_unix: float,
    *,
    quote_quality: str | None,
    open_price: float | None,
) -> dict[str, Any] | None:
    try:
        return apply_quote(
            symbol,
            price,
            volume,
            prev_close,
            ts_unix,
            quote_quality=quote_quality,
            open_price=open_price,
        )
    except TypeError:
        try:
            return apply_quote(
                symbol,
                price,
                volume,
                prev_close,
                ts_unix,
                quote_quality=quote_quality,
            )
        except TypeError:
            return apply_quote(symbol, price, volume, prev_close, ts_unix)
