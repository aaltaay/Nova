"""Post-connect startup reconciliation steps, guarded one by one.

Called once from the lifespan bootstrap after the IBKR connect wait. Each
step rebuilds a different piece of state a previous process left behind, so
one failure must never skip the ones after it.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["run_startup_reconciliation"]


def run_startup_reconciliation() -> None:
    from execution.startup_sweep import run_startup_sweep
    from nova_os.recovery import run_startup_recovery
    from strategy import risk as _risk

    steps = (
        ("Risk engine journal reconstruction", _risk.reconstruct_from_journal),
        ("Execution ledger startup sweep", run_startup_sweep),
        ("Nova OS startup recovery", run_startup_recovery),
    )
    for label, step in steps:
        try:
            step()
        except Exception:
            logger.exception("%s failed", label)
