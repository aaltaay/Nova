"""Nova's scheduled tasks and launchers start the trading path at Normal priority (2026-10-01).

Task Scheduler's default task priority (7) is BelowNormal CPU, Low I/O priority and memory priority
2, and a child inherits all three: the localhost watchdog's API and Vite, and the IB Gateway that
NovaDailyStart had launched, ran that way. Every registration now states its priority, and the
launchers raise themselves before they start anything.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "scripts"
_BACKEND = _REPO / "backend"
_POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


def _text(name: str) -> str:
    return (_SCRIPTS / name).read_text(encoding="ascii")


def _settings_commands(text: str) -> list[str]:
    """Each New-ScheduledTaskSettingsSet call, its backtick-continued lines joined."""
    lines = text.splitlines()
    calls = []
    for i, line in enumerate(lines):
        if "New-ScheduledTaskSettingsSet" not in line:
            continue
        parts = [line]
        while parts[-1].rstrip().endswith("`") and i + len(parts) < len(lines):
            parts.append(lines[i + len(parts)])
        calls.append(" ".join(p.rstrip().rstrip("`") for p in parts))
    return calls


def _function_body(text: str, name: str) -> str:
    start = text.index(f"function {name}")
    nxt = text.find("\nfunction ", start + 1)
    return text[start:] if nxt < 0 else text[start:nxt]


def test_every_task_registration_states_its_priority() -> None:
    seen = 0
    for path in sorted(_SCRIPTS.glob("*.ps1")):
        for call in _settings_commands(path.read_text(encoding="utf-8")):
            seen += 1
            assert re.search(r"-Priority\s+\S", call), f"{path.name}: no -Priority in: {call}"
    assert seen >= 3


@pytest.mark.parametrize("name", ["Register-NovaLocalhostWatchdog.ps1", "Install-NovaDailyTask.ps1"])
def test_trading_path_tasks_are_normal(name: str) -> None:
    (call,) = _settings_commands(_text(name))
    assert re.search(r"-Priority\s+4\b", call), call


def test_maintenance_stays_below_normal_on_purpose() -> None:
    text = _text("Ensure-NovaMaintenanceTask.ps1")
    assert "$priority = 7" in text
    (call,) = _settings_commands(text)
    assert "-Priority $priority" in call
    # The startup check re-registers a task saved at any other priority.
    assert "$task.Settings.Priority -eq $priority" in _function_body(text, "Test-MaintenanceTask")


def test_watchdog_raises_itself_before_starting_api_and_vite() -> None:
    common = _text("NovaLocalhost.Common.ps1")
    assert "NovaProcessPriority.ps1" in common
    for fn in ("Start-NovaApi", "Start-NovaVite"):
        body = _function_body(common, fn)
        assert body.index("Set-NovaLauncherPriority") < body.index("Start-Process"), fn
    watch = _text("Watch-NovaLocalhost.ps1")
    assert watch.index("Set-NovaLauncherPriority -Always") < watch.index("[void](Start-NovaLocalhostStack)")
    # A pull that changes the helper restarts the watchdog on the new code.
    assert "(Join-Path $PSScriptRoot 'NovaProcessPriority.ps1')" in watch


def test_daily_start_raises_itself_before_the_gateway() -> None:
    text = _text("Start-NovaDaily.ps1")
    raise_at = text.index("Set-NovaNormalPriority")
    calls = [m.start() for m in re.finditer(r"^\s*Start-IbGateway\s*$", text, re.M)]
    assert calls and all(raise_at < at for at in calls)
    assert raise_at < text.index("\nStart-NovaStack")


@pytest.mark.skipif(sys.platform != "win32" or not _POWERSHELL.exists(), reason="Windows PowerShell 5.1")
def test_powershell_launcher_and_repair_tool(tmp_path: Path) -> None:
    """From a process started like a priority-7 task: the launcher raises itself and its child
    inherits Normal; Repair-NovaPriority.ps1 -Apply raises a running process in place."""
    check = tmp_path / "check.ps1"
    check.write_text(
        textwrap.dedent(
            f"""
            $env:NOVA_REPO = '{tmp_path}'
            . '{_SCRIPTS / "NovaLocalhost.Common.ps1"}'
            $before = Format-NovaPriority (Get-NovaProcessPriority)
            Set-NovaLauncherPriority
            $after = Format-NovaPriority (Get-NovaProcessPriority)
            $child = Start-Process powershell.exe -ArgumentList '-NoProfile','-Command','Start-Sleep 20' -WindowStyle Hidden -PassThru
            Start-Sleep -Milliseconds 500
            $inherited = Format-NovaPriority (Get-NovaProcessPriority -ProcessId $child.Id)
            Stop-Process -Id $child.Id -Force
            @{{ before = $before; after = $after; child = $inherited }} | ConvertTo-Json -Compress
            """
        ),
        encoding="ascii",
    )
    driver = textwrap.dedent(
        f"""
        import json, subprocess, time
        from process_priority.normal import BELOW_NORMAL_PRIORITY_CLASS, _WindowsNative
        native = _WindowsNative()
        native.set_cpu_class(BELOW_NORMAL_PRIORITY_CLASS)
        native.set_io(1)
        native.set_memory(2)
        ps = [r"{_POWERSHELL}", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        launcher = subprocess.run(ps + [r"{check}"], capture_output=True, text=True, timeout=120)
        sleeper = subprocess.Popen(ps[:-1] + ["-Command", "Start-Sleep 30"])
        time.sleep(0.5)
        repair = subprocess.run(
            ps + [r"{_SCRIPTS / 'Repair-NovaPriority.ps1'}", "-ProcessId", str(sleeper.pid), "-Apply"],
            capture_output=True, text=True, timeout=120,
        )
        sleeper.kill()
        print(json.dumps({{"launcher": launcher.stdout, "repair": repair.stdout, "repair_rc": repair.returncode}}))
        """
    )
    done = subprocess.run(
        [sys.executable, "-c", driver], cwd=_BACKEND, capture_output=True, text=True, check=True, timeout=300,
    )
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    launcher = json.loads(seen["launcher"].strip().splitlines()[-1])
    assert launcher == {
        "before": "CPU BelowNormal, I/O Low, memory 2/5",
        "after": "CPU Normal, I/O Normal, memory 5/5",
        "child": "CPU Normal, I/O Normal, memory 5/5",
    }
    log = (tmp_path / "logs" / "nova-localhost-watch.log").read_text(encoding="utf-8")
    assert "priority raised CPU BelowNormal, I/O Low, memory 2/5 -> CPU Normal, I/O Normal, memory 5/5" in log
    assert seen["repair_rc"] == 0
    assert "-> CPU Normal, I/O Normal, memory 5/5" in seen["repair"]
    assert "Nothing was restarted" in seen["repair"]
