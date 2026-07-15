"""Client error intake — observability endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_client_errors_accepts_minimal_payload():
    res = client.post(
        "/api/client-errors",
        json={"message": "unit test boom", "source": "pytest"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True


def test_client_errors_rejects_huge_message_via_validation():
    huge = "x" * 5000
    res = client.post(
        "/api/client-errors",
        json={"message": huge, "source": "pytest"},
    )
    assert res.status_code == 422
