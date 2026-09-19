"""All 18 sensor endpoints return the common envelope."""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from sensors.registry import SENSOR_IDS, list_catalog
from sensors import memory_store, rings

client = TestClient(app)

SYMBOL_PATHS = (
    "/sensors/l2",
    "/sensors/tape",
    "/sensors/vwap",
    "/sensors/macd",
    "/sensors/rvol",
    "/sensors/day-volume",
    "/sensors/spread",
    "/sensors/flow",
    "/sensors/last-move",
    "/sensors/liquidity",
    "/sensors/emas",
    "/sensors/news",
    "/sensors/halt",
    "/sensors/memory",
    "/sensors/regime",
)

DESK_PATHS = (
    "/sensors/session-phase",
    "/sensors/risk",
    "/sensors/macro",
)


def setup_function() -> None:
    rings.reset_for_tests()
    memory_store.reset_for_tests()


def _assert_envelope(body: dict, sensor: str, *, symbol: str | None = None) -> None:
    assert body["sensor"] == sensor
    assert body["status"] in ("live", "stub", "computed_stub")
    assert isinstance(body["as_of"], (int, float))
    assert isinstance(body["data"], dict)
    if symbol is not None:
        assert body.get("symbol") == symbol


def test_catalog_lists_all_eighteen():
    res = client.get("/sensors")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 18
    keys = [row["sensor"] for row in body["sensors"]]
    assert keys == list(SENSOR_IDS)
    assert len(list_catalog()) == 18


def test_each_symbol_sensor_is_callable():
    for path in SYMBOL_PATHS:
        res = client.get(path, params={"symbol": "AAPL"})
        assert res.status_code == 200, path
        sensor = path.rsplit("/", 1)[-1]
        _assert_envelope(res.json(), sensor, symbol="AAPL")


def test_desk_sensors_are_callable():
    for path in DESK_PATHS:
        res = client.get(path)
        assert res.status_code == 200, path
        _assert_envelope(res.json(), path.rsplit("/", 1)[-1])


def test_snapshot_returns_eighteen():
    res = client.get("/sensors/snapshot", params={"symbol": "AAPL"})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 18
    assert len(body["sensors"]) == 18
    keys = [row["sensor"] for row in body["sensors"]]
    assert keys == list(SENSOR_IDS)


def test_bad_symbol_is_400():
    res = client.get("/sensors/l2", params={"symbol": "???"})
    assert res.status_code == 400


def test_memory_write_then_read():
    posted = client.post(
        "/sensors/memory",
        json={"symbol": "AAPL", "decision": "go", "confidence": 0.8, "note": "test"},
    )
    assert posted.status_code == 200
    assert posted.json()["data"]["appended"]["decision"] == "go"
    got = client.get("/sensors/memory", params={"symbol": "AAPL"})
    assert got.json()["status"] == "stub"
    assert got.json()["data"]["count"] == 1


def test_news_does_not_require_finnhub(monkeypatch):
    from advise import service

    monkeypatch.setattr(
        service,
        "latest",
        lambda symbol, depth=None: {
            "id": 7,
            "status": "complete",
            "finished_ts": 1_700_000_000,
            "stale": False,
            "transcript": [
                {"type": "message", "agent": "news", "content": "Catalyst: contract win."},
                {"type": "message", "agent": "sentiment", "content": "Tone is constructive."},
            ],
            "result": {"stance": "LONG", "reasons": ["Clean break"], "risks": []},
        },
    )
    res = client.get("/sensors/news", params={"symbol": "AAPL"})
    body = res.json()
    assert body["status"] == "live"
    assert body["data"]["source"] == "advice"
    assert body["data"]["headline"] == "Catalyst: contract win."
    assert body["data"]["sentiment"] == "bullish"
    assert "Advisor" not in str(body)
    assert "finnhub" not in str(body).lower()


def test_macro_is_stub_not_advice():
    res = client.get("/sensors/macro")
    body = res.json()
    assert body["status"] == "stub"
    kinds = {row["kind"] for row in body["data"]["events"]}
    assert {"FOMC", "CPI", "NFP"} <= kinds
    assert "advice" not in str(body["data"]["note"]).lower() or "Not Advice" in body["data"]["note"]


def test_risk_wires_existing_state(monkeypatch):
    from strategy.risk import RiskState, get_state

    state = get_state()
    state.reset_day()
    state.record_trade_result(-50)
    res = client.get("/sensors/risk")
    body = res.json()
    assert body["status"] == "live"
    assert body["data"]["consecutive_losses"] >= 1
    assert "daily_loss_limit_remaining" in body["data"]
    state.reset_day()
    assert isinstance(RiskState(), RiskState)


def test_session_phase_live():
    body = client.get("/sensors/session-phase").json()
    assert body["status"] == "live"
    assert body["data"]["phase"] in {
        "pre-market",
        "open auction",
        "morning momentum",
        "midday chop",
        "power hour",
        "after-hours",
        "closed",
    }
