"""Port probes + disconnect_hint for /api/ibkr/status."""
from __future__ import annotations

from unittest.mock import patch

from ibkr import gateway_heal as heal
from ibkr import port_diagnostics as ports


def setup_function() -> None:
    heal.clear_heal_status_for_tests()


def test_disconnect_hint_paper_refused_live_listening():
    assert (
        ports.disconnect_hint(
            connected=False,
            preferred_mode="paper",
            preferred_reachable=False,
            alternate_reachable=True,
        )
        == "paper_port_refused_live_listening"
    )


def test_disconnect_hint_none_when_connected():
    assert (
        ports.disconnect_hint(
            connected=True,
            preferred_mode="paper",
            preferred_reachable=False,
            alternate_reachable=True,
        )
        is None
    )


def test_status_port_fields_when_disconnected(monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")

    def _probe(_host, port, timeout=0.35):  # noqa: ARG001
        return port == 4001

    with patch.object(ports, "probe_port", side_effect=_probe):
        fields = ports.status_port_fields(connected=False)

    assert fields["preferred_port"] == 4002
    assert fields["alternate_port"] == 4001
    assert fields["preferred_port_reachable"] is False
    assert fields["alternate_port_reachable"] is True
    assert fields["disconnect_hint"] == "paper_port_refused_live_listening"


def test_status_port_fields_skips_alt_probe_when_connected(monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    with patch.object(ports, "probe_port") as mock_probe:
        fields = ports.status_port_fields(connected=True)
    mock_probe.assert_not_called()
    assert fields["preferred_port_reachable"] is True
    assert fields["disconnect_hint"] is None


def test_status_port_fields_probes_both_ports_at_once(monkeypatch):
    """#505: a dark Gateway costs one probe timeout, not one per port."""
    import threading

    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    both_in_flight = threading.Barrier(2, timeout=2.0)
    overlapped: list[int] = []

    def _probe(_host, port, timeout=0.35):  # noqa: ARG001
        both_in_flight.wait()  # BrokenBarrierError unless the other probe is running too
        overlapped.append(port)
        return False

    with patch.object(ports, "probe_port", side_effect=_probe):
        fields = ports.status_port_fields(connected=False)

    assert sorted(overlapped) == [4001, 4002]
    assert fields["disconnect_hint"] == "both_ports_unreachable"


def test_status_route_probes_off_the_http_loop(monkeypatch):
    """#505: GET /api/ibkr/status never runs a blocking port probe on the loop."""
    import threading

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ibkr import client as ibkr_client
    from ibkr import session_errors
    from routes.trading import router

    loop_threads: list[int] = []
    probe_threads: list[int] = []

    def _is_connected() -> bool:
        loop_threads.append(threading.get_ident())
        return False

    def _probe(_host, port, timeout=0.35):  # noqa: ARG001
        probe_threads.append(threading.get_ident())
        return port == 4002

    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setattr(ibkr_client, "is_connected", _is_connected)
    monkeypatch.setattr(ibkr_client, "is_ready", lambda: False)
    monkeypatch.setattr(ibkr_client, "is_enabled", lambda: False)
    monkeypatch.setattr(session_errors, "is_delayed_data", lambda: False)
    monkeypatch.setattr(ports, "probe_port", _probe)
    app = FastAPI()
    app.include_router(router)

    body = TestClient(app).get("/api/ibkr/status").json()

    assert body["disconnect_hint"] == "live_port_refused_paper_listening"
    assert len(probe_threads) == 2
    assert loop_threads and loop_threads[0] not in probe_threads
