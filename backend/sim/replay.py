"""Selected capture session for Sim replay (day + ticker)."""
from __future__ import annotations

from typing import Any

# None = synthetic SIM1 tape (default)
_date: str | None = None
_symbol: str | None = None


def reset_for_tests() -> None:
    global _date, _symbol
    _date = None
    _symbol = None


def status_payload() -> dict[str, Any]:
    capture = bool(_date and _symbol)
    return {
        "replay_date": _date,
        "replay_symbol": _symbol,
        "replay_source": "capture" if capture else "synthetic",
    }


def set_replay(date: str | None, symbol: str | None) -> dict[str, Any]:
    """Select a captured day/ticker, or clear to synthetic SIM1."""
    global _date, _symbol
    d = (date or "").strip() or None
    s = (symbol or "").strip().upper() or None
    if not d or not s:
        _date = None
        _symbol = None
    else:
        _date = d
        _symbol = s
    return status_payload()
