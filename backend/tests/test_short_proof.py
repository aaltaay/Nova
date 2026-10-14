"""Retired readiness permission, with real execution constraints kept (ADR 048 amendment, #791)."""
from ibkr import safety


def test_short_proof_route_is_retired():
    from main import app

    assert "/api/short-proof" not in {route.path for route in app.routes if hasattr(route, "path")}


def test_ibkr_status_has_no_proof_permission_or_progress():
    assert "short_proof" not in safety.status_snapshot()
