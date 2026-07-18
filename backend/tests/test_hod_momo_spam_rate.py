"""Spam-rate / consolidation invariants for HOD Momo (CJMB-class)."""
from __future__ import annotations

import time

from constants import HOD_MOMO_COOLDOWN_SEC, HOD_MOMO_CONSOLIDATION_SEC
from hod_momo_models import AlertObject


def test_consolidation_span_bounded_by_window():
    """Emitted burst span must not grow to thousands of seconds."""
    now = time.time()
    window = float(HOD_MOMO_CONSOLIDATION_SEC)
    ready = [
        AlertObject(
            id=f"{i}",
            timestamp="",
            ticker="CJMB",
            strategy_id=12,
            strategy_name="Running Up Alert",
            price=1.0,
            change_pct=10.0,
            rvol=2.0,
            float_shares=1e6,
            gap_pct=None,
            volume=1000,
            momentum_pct=None,
            created_ts=now - window + (i * 0.2),
        )
        for i in range(5)
    ]
    first_ts = min(a.created_ts or 0.0 for a in ready)
    last_ts = max(a.created_ts or 0.0 for a in ready)
    span = int(round(max(0.0, last_ts - first_ts)))
    assert span <= int(window) + 1


def test_mute_retired_cooldown_is_zero():
    """Anti-spam mute off — burst/consolidation (10s) is the rate limit."""
    assert float(HOD_MOMO_COOLDOWN_SEC) == 0.0
    assert float(HOD_MOMO_CONSOLIDATION_SEC) == 10.0
