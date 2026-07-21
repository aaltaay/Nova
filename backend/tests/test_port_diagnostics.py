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
