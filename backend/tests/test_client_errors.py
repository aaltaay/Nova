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


def test_client_errors_ignores_vite_hmr_noise():
    res = client.post(
        "/api/client-errors",
        json={
            "message": "send was called before connect",
            "stack": (
                "Error: send was called before connect\n"
                "    at Object.send (http://127.0.0.1:5173/@vite/client:384:15)"
            ),
            "source": "unhandledrejection",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert body.get("ignored") is True
    assert body.get("reason") == "dev_tooling_noise"


def test_client_errors_ignores_tradingview_object_disposed():
    res = client.post(
        "/api/client-errors",
        json={
            "message": "Uncaught Error: Object is disposed",
            "source": "window.onerror",
            "url": "http://127.0.0.1:5173/",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert body.get("ignored") is True
    assert body.get("reason") == "dev_tooling_noise"
