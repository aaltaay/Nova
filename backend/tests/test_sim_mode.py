"""In-app Sim toggle + status overlay. Env is bootstrap only."""
from __future__ import annotations

from pathlib import Path

from sim.mode import is_sim_mode, persist_nova_broker, reset_for_tests, set_sim_mode
from sim.status import overlay_ibkr_status


def setup_function() -> None:
    reset_for_tests()


def teardown_function() -> None:
    reset_for_tests()


def test_default_is_not_sim() -> None:
    assert is_sim_mode() is False


def test_toggle_on_and_off() -> None:
    payload = set_sim_mode(True)
    assert is_sim_mode() is True
    assert payload["sim"] is True
    assert payload["sim_symbol"] == "SIM1"
    assert payload["mode"] == "sim"
    off = set_sim_mode(False)
    assert is_sim_mode() is False
    assert off["sim"] is False


def test_overlay_forces_sim_even_when_gateway_looks_live() -> None:
    set_sim_mode(True)
    out = overlay_ibkr_status({
        "mode": "live",
        "connected": False,
        "enabled": False,
        "spend_status": "locked",
        "transport_connected": True,
        "session_state": "disconnected",
    })
    assert out["mode"] == "sim"
    assert out["connected"] is True
    assert out["enabled"] is True
    assert out["spend_status"] == "sim_armed"
    assert out["sim"] is True
    assert out["sim_symbol"] == "SIM1"


def test_overlay_passthrough_when_off() -> None:
    out = overlay_ibkr_status({"mode": "paper", "connected": False})
    assert out["mode"] == "paper"
    assert out["sim"] is False


def test_scan_injects_sim1() -> None:
    from sim.scan import with_sim_row

    assert with_sim_row([]) == []
    set_sim_mode(True)
    rows = with_sim_row([{"symbol": "AAPL", "price": 1}])
    assert rows[0]["symbol"] == "SIM1"
    assert rows[1]["symbol"] == "AAPL"


def test_persist_rewrites_env(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("IBKR_ENABLED=true\n", encoding="utf-8")
    assert persist_nova_broker("sim", env_path=env) is True
    text = env.read_text(encoding="utf-8")
    assert "NOVA_BROKER=sim" in text
    assert persist_nova_broker("ibkr", env_path=env) is True
    assert "NOVA_BROKER=ibkr" in env.read_text(encoding="utf-8")
