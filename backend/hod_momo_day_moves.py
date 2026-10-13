"""HOD Momo's day change and gap from an IBKR quote: previous close from the quote, else from the board row.

The IBKR enrichment pass wrote ``change_pct`` only when its own quote carried a previous close and never wrote
``gap_pct`` at all, so a name the boards priced from a known close (PFAI, 2026-10-13: prev_close 2.61 on Gappers)
alerted all premarket with no change % -- and Strategy 5, which needs one, could not fire on it.
"""
from __future__ import annotations

from typing import Any


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def board_prev_close(symbol: str) -> float | None:
    """The previous close the Gappers / Gainers / After Hours rows carry for ``symbol``, or ``None``."""
    try:
        from runtime_state import get_runtime_state

        state = get_runtime_state()
    except Exception:  # noqa: BLE001 -- no runtime state (tests, early start): the quote alone decides
        return None
    want = (symbol or "").strip().upper()
    for rows in (state.gapper_cache, state.gainer_cache, state.afterhours_cache):
        for row in rows or []:
            if (row.get("symbol") or "").strip().upper() != want:
                continue
            close = _positive(row.get("prev_close") or row.get("previous_close"))
            if close is not None:
                return close
    return None


def day_moves(symbol: str, price: float, quote: dict[str, Any]) -> tuple[float | None, float | None]:
    """``(change_pct, gap_pct)``: change from the previous close; gap from it to today's open.

    ``quote["open"]`` is today's open only after 09:30 (``ibkr.open_tick.todays_open``), so the gap stays
    unknown before the open, as the scanner schema states. Unknown is ``None``, never 0.
    """
    prev = _positive(quote.get("prev_close")) or board_prev_close(symbol)
    if prev is None:
        return None, None
    change = (float(price) - prev) / prev * 100.0
    opened = _positive(quote.get("open"))
    gap = (opened - prev) / prev * 100.0 if opened is not None else None
    return change, gap
