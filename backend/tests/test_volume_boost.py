"""Volume boost engine + thin REST -- fixtures only, no live IBKR."""
from __future__ import annotations

from fastapi.testclient import TestClient

import hod_momo_metrics as metrics
import volume_boost as vb
from constants import (
    VOLUME_BOOST_DEBOUNCE_SEC,
    VOLUME_BOOST_SPIKE_WINDOW_SEC,
    VOLUME_BOOST_TOP_N,
)
from main import app
from tests.test_volume_boost_detect import _samples_flat_then_spike


client = TestClient(app)


def setup_function() -> None:
    metrics.clear_volume_buffers()
    vb.reset_for_tests()


def _replay(symbol: str, samples: list[tuple[float, int]], price: float = 4.25) -> None:
    for ts, vol in samples:
        vb.observe_l1(symbol, vol, price, ts)


def test_observe_does_not_admit_until_debounce():
    samples, now = _samples_flat_then_spike()
    _replay("ABC", samples[:-1])
    vb.observe_l1("ABC", samples[-1][1], 4.25, now)
    view = vb.build_view(now=now)
    assert view["volume_boost"] == []
    vb.observe_l1("ABC", samples[-1][1] + 10, 4.30, now + VOLUME_BOOST_DEBOUNCE_SEC)
    admitted = vb.build_view(now=now + VOLUME_BOOST_DEBOUNCE_SEC)
    assert [r["symbol"] for r in admitted["volume_boost"]] == ["ABC"]
    assert admitted["volume_boost"][0]["status"] == "hot"
    assert admitted["volume_boost"][0]["price"] == 4.30
    assert admitted["volume_boost"][0]["age_sec"] == VOLUME_BOOST_DEBOUNCE_SEC
    assert admitted["volume_boost"][0]["spike_ratio"] >= 5


def test_build_view_caps_top_n_and_skips_unadmitted(monkeypatch):
    samples, now = _samples_flat_then_spike()
    for i in range(VOLUME_BOOST_TOP_N + 3):
        sym = f"S{i:02d}"
        _replay(sym, samples)
        vb.observe_l1(sym, samples[-1][1], 1.0 + i, now + VOLUME_BOOST_DEBOUNCE_SEC)
    view = vb.build_view(now=now + VOLUME_BOOST_DEBOUNCE_SEC)
    assert len(view["volume_boost"]) == VOLUME_BOOST_TOP_N
    monkeypatch.setattr(vb, "_ibkr_ready", lambda: True)
    monkeypatch.setattr(vb, "_bridge_error", lambda: None)
    live = vb.build_view(now=now + VOLUME_BOOST_DEBOUNCE_SEC)
    assert live["table_state"] == "live"
    assert live["feed_error"] is None


def test_build_view_loud_when_ibkr_down_and_empty(monkeypatch):
    monkeypatch.setattr(vb, "_ibkr_ready", lambda: False)
    monkeypatch.setattr(vb, "_bridge_error", lambda: None)
    view = vb.build_view(now=1.0)
    assert view["volume_boost"] == []
    assert view["table_state"] == "unavailable"
    assert view["feed_error"]


def test_get_volume_boost_route_is_thin(monkeypatch):
    seen = {}

    def _fake():
        seen["hit"] = True
        return {"rev": "test", "volume_boost": [], "table_state": "live", "feed_error": None}

    monkeypatch.setattr("routes.volume_boost.build_view", _fake)
    res = client.get("/api/volume-boost")
    assert res.status_code == 200
    assert seen["hit"] is True
    assert res.json()["volume_boost"] == []


def test_observe_l1_from_apply_does_not_need_hod(monkeypatch):
    """Scanner L1 volume is enough -- HOD active-set is not required."""
    from ibkr import l1_apply

    samples, now = _samples_flat_then_spike()
    monkeypatch.setattr("hod_tick_feed.feed_hod_on_tick", lambda *a, **k: None)
    for ts, vol in samples:
        l1_apply.apply_l1_quote("XYZ", 3.5, vol, 3.0, ts)
    l1_apply.apply_l1_quote("XYZ", 3.6, samples[-1][1] + 5, 3.0, now + VOLUME_BOOST_DEBOUNCE_SEC)
    rows = vb.build_view(now=now + VOLUME_BOOST_DEBOUNCE_SEC)["volume_boost"]
    assert [r["symbol"] for r in rows] == ["XYZ"]
    assert VOLUME_BOOST_SPIKE_WINDOW_SEC == 60.0
