"""IB Gateway launch/focus helper — no real process spawn in unit tests."""
from __future__ import annotations

from pathlib import Path

from ibkr import launch_gateway as lg


def test_resolve_exe_prefers_env(monkeypatch, tmp_path: Path):
    exe = tmp_path / "ibgateway.exe"
    exe.write_bytes(b"x")
    monkeypatch.setenv("IBKR_GATEWAY_EXE", str(exe))
    assert lg._resolve_gateway_exe() == exe


def test_resolve_exe_ibc_renamed(monkeypatch, tmp_path: Path):
    root = tmp_path / "ibgateway"
    ver = root / "1045"
    ver.mkdir(parents=True)
    exe1 = ver / "ibgateway1.exe"
    exe1.write_bytes(b"x")
    monkeypatch.delenv("IBKR_GATEWAY_EXE", raising=False)
    monkeypatch.setattr(lg, "IBKR_GATEWAY_EXE_DEFAULT", str(ver / "ibgateway.exe"))
    monkeypatch.setattr(lg, "IBKR_GATEWAY_ROOT", str(root))
    assert lg._resolve_gateway_exe() == exe1


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

    def fake_start(path: Path, *, via_powershell: bool = False, extra_args=None):
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


def test_mode_launch_attaches_when_target_port_already_open(monkeypatch):
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: True)
    monkeypatch.setattr(lg, "_probe_api_port", lambda port: port == 4001)
    stopped: list[bool] = []
    started: list[tuple] = []
    monkeypatch.setattr(lg, "_stop_gateway_process", lambda: stopped.append(True) or True)
    monkeypatch.setattr(lg, "_start_process", lambda *a, **k: started.append((a, k)))
    monkeypatch.setattr(lg, "_align_ibc_trading_mode", lambda _mode: None)
    monkeypatch.setattr(lg, "_apply_nova_gateway_mode", lambda _mode: None)
    monkeypatch.setattr(lg, "_focus_gateway_window", lambda: True)
    out = lg.launch_or_focus_gateway("live")
    assert out["ok"] is True
    assert out["action"] == "already_listening"
    assert stopped == []
    assert started == []


def test_mode_launch_does_not_kill_authenticating_gateway(monkeypatch):
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: True)
    monkeypatch.setattr(lg, "_probe_api_port", lambda _port: False)
    stopped: list[bool] = []
    started: list[tuple] = []
    monkeypatch.setattr(lg, "_stop_gateway_process", lambda: stopped.append(True) or True)
    monkeypatch.setattr(lg, "_start_process", lambda *a, **k: started.append((a, k)))
    monkeypatch.setattr(lg, "_align_ibc_trading_mode", lambda _mode: None)
    monkeypatch.setattr(lg, "_apply_nova_gateway_mode", lambda _mode: None)
    monkeypatch.setattr(lg, "_focus_gateway_window", lambda: True)
    out = lg.launch_or_focus_gateway("live")
    assert out["ok"] is True
    assert out["action"] == "focused_authenticating"
    assert stopped == []
    assert started == []


def test_mode_launch_spawns_second_door_without_killing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: True)
    monkeypatch.setattr(lg, "_probe_api_port", lambda port: port == 4002)
    stopped: list[bool] = []
    stopped_ports: list[tuple] = []
    monkeypatch.setattr(lg, "_stop_gateway_process", lambda: stopped.append(True) or True)
    monkeypatch.setattr(lg, "_stop_listen_ports", lambda *ports: stopped_ports.append(ports))
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
    assert stopped == []
    assert stopped_ports == []
    assert started == [(launcher, True, ["-TradingMode", "live"])]


def test_mode_launch_force_restart_kills_listening_port(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: False)
    monkeypatch.setattr(lg, "_probe_api_port", lambda port: port == 4001)
    stopped_ports: list[tuple] = []
    monkeypatch.setattr(
        lg,
        "_stop_listen_ports",
        lambda *ports: stopped_ports.append(ports),
    )
    monkeypatch.setattr(lg, "_stop_gateway_process", lambda: True)
    launcher = tmp_path / "start_gateway.ps1"
    launcher.write_text("#", encoding="utf-8")
    monkeypatch.setattr(lg, "_ibc_launcher", lambda: launcher)
    monkeypatch.setattr(lg, "_align_ibc_trading_mode", lambda _mode: None)
    monkeypatch.setattr(lg, "_apply_nova_gateway_mode", lambda _mode: None)
    started: list[tuple] = []

    def fake_start(path: Path, *, via_powershell: bool = False, extra_args=None):
        started.append((path, via_powershell, list(extra_args or [])))

    monkeypatch.setattr(lg, "_start_process", fake_start)
    out = lg.launch_or_focus_gateway("paper", force_restart=True)
    assert out["ok"] is True
    assert out["action"] == "launched_ibc"
    assert stopped_ports == [(4002, 4001)]
    assert started == [(launcher, True, ["-TradingMode", "paper"])]


def test_mode_launch_force_live_uses_ibc(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(lg.os, "name", "nt")
    monkeypatch.setattr(lg, "_gateway_process_running", lambda: False)
    monkeypatch.setattr(lg, "_probe_api_port", lambda _port: False)
    stopped_ports: list[tuple] = []
    monkeypatch.setattr(
        lg,
        "_stop_listen_ports",
        lambda *ports: stopped_ports.append(ports),
    )
    monkeypatch.setattr(lg, "_stop_gateway_process", lambda: True)
    launcher = tmp_path / "start_gateway.ps1"
    launcher.write_text("#", encoding="utf-8")
    monkeypatch.setattr(lg, "_ibc_launcher", lambda: launcher)
    monkeypatch.setattr(lg, "_align_ibc_trading_mode", lambda _mode: None)
    monkeypatch.setattr(lg, "_apply_nova_gateway_mode", lambda _mode: None)
    cleared: list[bool] = []
    monkeypatch.setattr("ibkr.jts_ini.clear_restart_token", lambda: cleared.append(True))
    monkeypatch.setattr(lg, "_focus_gateway_window", lambda: True)
    started: list[tuple] = []

    def fake_start(path: Path, *, via_powershell: bool = False, extra_args=None):
        started.append((path, via_powershell, list(extra_args or [])))

    monkeypatch.setattr(lg, "_start_process", fake_start)
    out = lg.launch_or_focus_gateway("live", force_restart=True)
    assert out["ok"] is True
    assert out["action"] == "launched_ibc"
    assert stopped_ports == [(4001, 4002)]
    assert cleared == [True]
    assert started == [(launcher, True, ["-TradingMode", "live"])]


def test_clear_jts_restart_token(tmp_path: Path, monkeypatch):
    from ibkr.jts_ini import clear_restart_token

    ini = tmp_path / "jts.ini"
    ini.write_text("[Logon]\nRestart=OK\ntradingMode=l\n", encoding="utf-8")
    monkeypatch.setattr("ibkr.jts_ini.IBKR_JTS_INI_PATHS", (ini,))
    clear_restart_token()
    text = ini.read_text(encoding="utf-8")
    assert "Restart=\n" in text
    assert "Restart=OK" not in text


def test_align_ibc_live_clears_week_token(monkeypatch, tmp_path: Path):
    ini = tmp_path / "config.ini"
    ini.write_text(
        "TradingMode=paper\nOverrideTwsApiPort=4002\n"
        "AutoRestartTime=11:45 PM\nAutoLogoffTime=\n"
        "IbLoginId=paperuser\nIbLoginIdLive=liveuser\nIbLoginIdPaper=paperuser\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(lg, "_ibc_dir", lambda: tmp_path)
    lg._align_ibc_trading_mode("live")
    text = ini.read_text(encoding="utf-8")
    assert "TradingMode=live" in text
    assert "OverrideTwsApiPort=4001" in text
    assert "AutoRestartTime=\n" in text
    assert "AutoLogoffTime=11:45 PM" in text
    assert "IbLoginId=liveuser" in text
    lg._align_ibc_trading_mode("paper")
    text = ini.read_text(encoding="utf-8")
    assert "TradingMode=paper" in text
    assert "AutoRestartTime=11:45 PM" in text
    assert "AutoLogoffTime=\n" in text
    assert "IbLoginId=paperuser" in text


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
