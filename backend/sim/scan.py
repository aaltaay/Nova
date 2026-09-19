"""Inject SIM1 onto scanner REST lists so Look Up / ticker click works."""
from __future__ import annotations

from typing import Any

from constants_sim import SIM_SYMBOL
from sim.mode import is_sim_mode


def with_sim_row(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not is_sim_mode():
        return rows
    from sim import market as _market

    row = _market.gainer_row()
    rest = [
        r for r in rows if str(r.get("symbol") or "").strip().upper() != SIM_SYMBOL
    ]
    return [row] + rest
