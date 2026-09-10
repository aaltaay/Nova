"""HTTP acknowledgment for the IBKR verification-required entry latch."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from execution import verification_gate
from routes.trading_execution import router

app = FastAPI()
app.include_router(router, prefix="/api/ibkr")


def test_acknowledge_verification_clears_only_requested_symbol() -> None:
    verification_gate.reset_for_tests()
    verification_gate.latch("AAPL")
    verification_gate.latch("MSFT")

    with TestClient(app) as client:
        response = client.post("/api/ibkr/verification/aapl/acknowledge")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "symbol": "AAPL", "cleared": True}
    assert verification_gate.blocked_symbols() == ("MSFT",)
    verification_gate.reset_for_tests()
