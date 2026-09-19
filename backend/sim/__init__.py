"""Local Sim Feed + Sim Fill -- practice harness, not an IBKR adapter."""
from __future__ import annotations

from sim.mode import desk_connected, is_sim_mode, reset_for_tests, set_sim_mode

__all__ = [
    "desk_connected",
    "is_sim_mode",
    "reset_for_tests",
    "set_sim_mode",
]
