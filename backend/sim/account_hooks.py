"""Sim early-returns for ibkr.account -- keeps that file under 400."""
from __future__ import annotations

from typing import Any


def positions_if_sim() -> list[dict[str, Any]] | None:
    from sim.mode import is_sim_mode

    if not is_sim_mode():
        return None
    from sim import broker as _sim_broker

    return _sim_broker.positions()


def summary_if_sim() -> dict[str, Any] | None:
    from sim.mode import is_sim_mode

    if not is_sim_mode():
        return None
    from sim import broker as _sim_broker

    return _sim_broker.account_summary()
