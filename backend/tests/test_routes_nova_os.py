"""The desk event log route (backend/routes/nova_os.py).

ADR 025 retired the decide / policy routes; only /events stays.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nova_os.events_db as events_db
from main import app
from nova_os.events import KIND_SYSTEM, record_receipt

client = TestClient(app)


def test_events_returns_recent_receipts():
    events_db.init_db()
    record_receipt(kind=KIND_SYSTEM, payload={"event": "risk_halt", "reason": "test"})
    res = client.get("/api/nova-os/events?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    assert body["events"][0]["payload"]["event"] == "risk_halt"


def test_retired_decide_and_policy_routes_are_gone():
    assert client.get("/api/nova-os/decide").status_code == 404
    assert client.get("/api/nova-os/decide/AAPL").status_code == 404
    assert client.get("/api/nova-os/policy").status_code == 404
