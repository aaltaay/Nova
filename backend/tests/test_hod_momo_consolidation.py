"""Consolidation must not drop distinct strategies for the same ticker."""
from __future__ import annotations

import asyncio
import time

import hod_momo as hm
import hod_momo_alerts as alerts
import hod_momo_persist as persist
from hod_momo_models import AlertObject
from hod_momo_state import HodMomoState


def _alert(sid: int, name: str, now: float) -> AlertObject:
    return AlertObject(
        id=f"{int(now * 1000)}-LBGJ-{sid}",
        timestamp="",
        ticker="LBGJ",
        strategy_id=sid,
        strategy_name=name,
        price=2.4,
        change_pct=30.0,
        rvol=10.0,
        float_shares=178_863,
        gap_pct=None,
        volume=1_000_000,
        momentum_pct=None,
        created_ts=now,
    )


def test_flush_emits_one_alert_per_strategy(monkeypatch):
    """Fixture prices are fake — never persist to the live `.cache` alerts file."""
    hm.replace_state(HodMomoState())
    state = hm.get_state()
    monkeypatch.setattr(persist, "save_alerts", lambda **_kw: None)
    monkeypatch.setattr(persist, "flush_pending_alert_save", lambda: None)
    monkeypatch.setattr(
        "alerts.hooks.notify_hod_alert_async",
        lambda *_a, **_k: None,
    )
    now = time.time()
    state.pending_consolidation["LBGJ"] = [
        (now - 1.0, _alert(1, "Former Momo Stock", now - 0.5)),
        (now - 1.0, _alert(7, "Low Float - High Rel Vol", now)),
    ]

    async def _once() -> None:
        task = asyncio.create_task(alerts.flush_consolidated_loop())
        await asyncio.sleep(1.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_once())
    names = {a.strategy_name for a in state.today_alerts}
    assert "Former Momo Stock" in names
    assert "Low Float - High Rel Vol" in names
