"""IB Gateway launch/focus helper — no real process spawn in unit tests."""
from __future__ import annotations

from pathlib import Path

from ibkr import launch_gateway as lg


def test_resolve_exe_prefers_env(monkeypatch, tmp_path: Path):
    exe = tmp_path / "ibgateway.exe"
    exe.write_bytes(b"x")
    monkeypatch.setenv("IBKR_GATEWAY_EXE", str(exe))
    assert lg._resolve_gateway_exe() == exe


def test_resolve_exe_missing_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("IBKR_GATEWAY_EXE", str(tmp_path / "missing.exe"))
    monkeypatch.setattr(lg, "IBKR_GATEWAY_EXE_DEFAULT", str(tmp_path / "also-missing.exe"))
    monkeypatch.setattr(lg, "IBKR_GATEWAY_ROOT", str(tmp_path / "empty-root"))
    assert lg._resolve_gateway_exe() is None


def test_launch_focuses_when_already_running(monkeypatch):
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: True)
    monkeypatch.setattr(lg, "_focus_gateway_window", lambda: True)
    out = lg.launch_or_focus_gateway()
    assert out["ok"] is True
    assert out["action"] == "focused"


def test_launch_starts_exe_when_idle(monkeypatch, tmp_path: Path):
    exe = tmp_path / "ibgateway.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: False)
    monkeypatch.setattr(lg, "_ibc_launcher", lambda: None)
    monkeypatch.setattr(lg, "_resolve_gateway_exe", lambda: exe)
    monkeypatch.setattr(lg, "_focus_gateway_window", lambda: False)
    started: list[Path] = []

    def fake_start(path: Path, *, via_powershell: bool = False):
        started.append(path)

    monkeypatch.setattr(lg, "_start_process", fake_start)
    out = lg.launch_or_focus_gateway()
    assert out["ok"] is True
    assert out["action"] == "launched"
    assert started == [exe]


def test_launch_unsupported_on_non_windows(monkeypatch):
    monkeypatch.setattr(lg.os, "name", "posix")
    out = lg.launch_or_focus_gateway()
    assert out["ok"] is False
    assert out["action"] == "unsupported"


def test_mode_launch_restarts_running_gateway(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: True)
    stopped: list[bool] = []
    monkeypatch.setattr(lg, "_stop_gateway_process", lambda: stopped.append(True) or True)
    launcher = tmp_path / "start_gateway.ps1"
    launcher.write_text("#", encoding="utf-8")
    monkeypatch.setattr(lg, "_ibc_launcher", lambda: launcher)
    monkeypatch.setattr(lg, "_align_ibc_trading_mode", lambda _mode: None)
    monkeypatch.setattr(lg, "_apply_nova_gateway_mode", lambda _mode: None)
    started: list[tuple] = []

    def fake_start(path: Path, *, via_powershell: bool = False, extra_args=None):
        started.append((path, via_powershell, list(extra_args or [])))

    monkeypatch.setattr(lg, "_start_process", fake_start)
    out = lg.launch_or_focus_gateway("live")
    assert out["ok"] is True
    assert out["action"] == "launched_ibc"
    assert out["mode"] == "live"
    assert stopped == [True]
    assert started == [(launcher, True, ["-TradingMode", "live"])]


def test_mode_launch_rejects_garbage(monkeypatch):
    monkeypatch.setattr(lg.os, "name", "nt")
    out = lg.launch_or_focus_gateway("demo")
    assert out["ok"] is False
    assert out["action"] == "invalid_mode"


def test_rewrite_ini_key_first_match_only(tmp_path: Path):
    ini = tmp_path / "config.ini"
    ini.write_text("TradingMode=paper\nOther=1\nTradingMode=ignore\n", encoding="utf-8")
    assert lg._rewrite_ini_key(ini, "TradingMode", "live") is True
    assert ini.read_text(encoding="utf-8") == "TradingMode=live\nOther=1\nTradingMode=ignore\n"
