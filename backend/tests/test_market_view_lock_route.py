"""The desk's order-lock flips land in the backend log (ADR 045 amendment, operator ask 2026-10-13)."""
from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from main import app

WHY = ("No Level 2 for VLO: IBKR refused this Level 2 (IB error 309): all 3 of its Level 2 lines are in use. "
       "Orders are locked until a Level 2 is live. Flatten and cancels still work.")


def test_a_lock_and_its_release_are_one_log_line_each(caplog):
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="nova.order_lock"):
        on = client.post("/api/market-view/lock", json={"schema_version": 1, "symbol": "vlo", "locked": True,
                                                        "reason": WHY, "locked_for_ms": None})
        off = client.post("/api/market-view/lock", json={"schema_version": 1, "symbol": "VLO", "locked": False,
                                                         "reason": None, "locked_for_ms": 3200})
    assert on.json() == {"ok": True} and off.json() == {"ok": True}
    lines = [r.getMessage() for r in caplog.records if r.name == "nova.order_lock"]
    assert lines == [f"order lock ON  VLO -- {WHY}", "order lock OFF VLO -- open again after 3.2 s"]


def test_an_unknown_schema_version_is_refused():
    response = TestClient(app).post("/api/market-view/lock", json={"schema_version": 2, "symbol": "VLO",
                                                                   "locked": True})
    assert response.status_code == 422
