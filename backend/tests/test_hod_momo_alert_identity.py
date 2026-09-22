"""HOD alert identity and honesty (QA V16, C32, C33, C34)."""
from __future__ import annotations

import json
import math
import time

import hod_momo_alerts
import hod_momo_market
import hod_momo_state
from hod_momo_debug import build_debug_snaps
from hod_momo_models import AlertObject, TickerSnap, alert_from_dict, alert_to_dict, new_alert


def _alert(created_ts: float, trade_ts: float, snap: TickerSnap | None = None) -> AlertObject:
    return new_alert(
        symbol="VEEE",
        strategy_id=12,
        strategy_name="Running Up Alert",
        price=16.95,
        snap=snap or TickerSnap(price=16.95),
        momentum_pct=None,
        trade_ts=trade_ts,
        created_ts=created_ts,
    )


def test_two_alerts_on_one_stale_print_get_distinct_ids():
    # 2026-09-22: VEEE fired at 1790046029.9 and 1790046256.1 on the same
    # 02:29:05 print; both carried id 1790044145000-VEEE-12.
    stale_print = 1_790_044_145.0
    first = _alert(created_ts=1_790_046_029.5, trade_ts=stale_print)
    second = _alert(created_ts=1_790_046_256.25, trade_ts=stale_print)
    assert first.id != second.id
    assert first.id == "1790046029500-VEEE-12"
    # The row still says when the trigger print happened.
    assert first.timestamp == second.timestamp == "2026-09-22T02:29:05.000Z"


def test_change_pct_stays_absent_instead_of_an_invented_zero():
    assert _alert(1.0, 1.0, TickerSnap(price=2.0, change_pct=None)).change_pct is None
    assert _alert(1.0, 1.0, TickerSnap(price=2.0, change_pct=0.0)).change_pct == 0.0
    assert _alert(1.0, 1.0, TickerSnap(price=2.0, change_pct=12.5)).change_pct == 12.5
    restored = alert_from_dict({"id": "x", "ticker": "X", "price": 1.0})
    assert restored.change_pct is None


def test_alert_to_dict_never_carries_nan():
    alert = _alert(1.0, 1.0, TickerSnap(price=2.0, rvol=math.nan, gap_pct=math.inf))
    payload = alert_to_dict(alert)
    assert payload["rvol"] is None and payload["gap_pct"] is None
    json.dumps(payload, allow_nan=False)


def test_ws_initial_payload_is_strict_json_with_a_nan_alert(monkeypatch):
    state = hod_momo_state.get_state()
    prev = list(state.today_alerts)
    try:
        state.today_alerts = [_alert(2.0, 2.0, TickerSnap(price=3.0, rvol=math.nan))]
        text = json.dumps(hod_momo_alerts.get_ws_initial_payload(), allow_nan=False)
        assert json.loads(text)["alerts"][0]["rvol"] is None
    finally:
        state.today_alerts = prev


def test_last_enriched_is_epoch_seconds(monkeypatch):
    monkeypatch.setattr(hod_momo_market.time, "time", lambda: 1_790_050_000.0)
    monkeypatch.setattr(hod_momo_market.time, "monotonic", lambda: 37_217.0)
    state = hod_momo_state.get_state()
    prev = dict(state.ticker_snaps)
    try:
        hod_momo_market.update_ticker_snapshot("GRAL", 109.02, rvol=1.5, change_pct=2.0)
        snap = state.ticker_snaps["GRAL"]
        assert snap.last_enriched == 1_790_050_000.0
        row = next(r for r in build_debug_snaps({"GRAL": snap}) if r["symbol"] == "GRAL")
        assert abs(row["last_enriched"] - 1_790_050_000.0) < 1e-6
        assert row["last_enriched"] > time.time() - 10 * 365 * 24 * 3600
    finally:
        state.ticker_snaps.clear()
        state.ticker_snaps.update(prev)
