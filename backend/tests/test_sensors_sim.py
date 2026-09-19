"""SIM1 sensors read the local Sim feed when Sim is on."""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from sensors import rings
from sim import market as sim_market
from sim.mode import reset_for_tests, set_sim_mode

client = TestClient(app)


def setup_function() -> None:
    reset_for_tests()
    rings.reset_for_tests()
    set_sim_mode(True)
    for _ in range(40):
        sim_market.step()


def teardown_function() -> None:
    reset_for_tests()
    rings.reset_for_tests()


def test_sim1_l2_tape_volume_are_live():
    l2 = client.get("/sensors/l2", params={"symbol": "SIM1"}).json()
    assert l2["status"] == "live"
    assert l2["data"].get("source") == "sim"
    assert l2["data"]["bids"]
    tape = client.get("/sensors/tape", params={"symbol": "SIM1"}).json()
    assert tape["data"]["print_count"] >= 1
    day = client.get("/sensors/day-volume", params={"symbol": "SIM1"}).json()
    assert day["data"]["day_volume"]
    vwap = client.get("/sensors/vwap", params={"symbol": "SIM1"}).json()
    assert "error" not in vwap or vwap["data"].get("vwap") is not None or vwap["data"].get("bars") is not None


def test_snapshot_defaults_to_sim1_when_sim_on():
    res = client.get("/sensors/snapshot")
    assert res.status_code == 200
    assert res.json()["symbol"] == "SIM1"
    assert res.json()["count"] == 18
