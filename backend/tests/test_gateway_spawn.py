"""Open live/paper must start IBC with credentials -- not an empty Gateway exe."""
from __future__ import annotations

from pathlib import Path

from ibkr.gateway_login_fill import Credentials
from ibkr.gateway_spawn import spawn_mode_gateway


def _start_ok(started: list):
    def start(path: Path, *, via_powershell: bool = False, extra_args=None):
        started.append((path, via_powershell, list(extra_args or [])))

    return start


def test_spawn_mode_refuses_empty_login_without_ibc_credentials(tmp_path: Path, monkeypatch):
    exe = tmp_path / "ibgateway.exe"
    exe.write_bytes(b"x")
    started: list = []
    monkeypatch.setattr(
        "ibkr.gateway_spawn.load_ibc_credentials",
        lambda: None,
    )
    out = spawn_mode_gateway(
        "live",
        ibc=tmp_path / "start_gateway.ps1",
        exe=exe,
        start=_start_ok(started),
        focus=lambda: True,
    )
    assert out["ok"] is False
    assert out["action"] == "missing_credentials"
    assert "username" in out["message"].lower()
    assert "password" in out["message"].lower()
    assert started == []


def test_spawn_mode_refuses_raw_exe_when_ibc_launcher_missing(tmp_path: Path, monkeypatch):
    exe = tmp_path / "ibgateway.exe"
    exe.write_bytes(b"x")
    started: list = []
    monkeypatch.setattr(
        "ibkr.gateway_spawn.load_ibc_credentials",
        lambda: Credentials(username="liveuser", password="secret"),
    )
    out = spawn_mode_gateway(
        "live",
        ibc=None,
        exe=exe,
        start=_start_ok(started),
        focus=lambda: True,
    )
    assert out["ok"] is False
    assert out["action"] == "missing_ibc"
    assert "ibc" in out["message"].lower()
    assert started == []


def test_spawn_mode_starts_ibc_when_credentials_exist(tmp_path: Path, monkeypatch):
    launcher = tmp_path / "start_gateway.ps1"
    launcher.write_text("#", encoding="utf-8")
    started: list = []
    monkeypatch.setattr(
        "ibkr.gateway_spawn.load_ibc_credentials",
        lambda: Credentials(username="liveuser", password="secret"),
    )
    out = spawn_mode_gateway(
        "live",
        ibc=launcher,
        exe=None,
        start=_start_ok(started),
        focus=lambda: True,
    )
    assert out["ok"] is True
    assert out["action"] == "launched_ibc"
    assert "username/password" in out["message"].lower()
    assert started == [(launcher, True, ["-TradingMode", "live"])]
