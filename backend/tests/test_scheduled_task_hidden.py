"""Nova's hidden scheduled tasks never draw a console window (2026-10-01).

`powershell.exe -WindowStyle Hidden` hides its console only after the console has drawn, so the
localhost watchdog's 5-minute kick flashed a black Windows Terminal window on the desk every time:
103 times that day, each a duplicate that found the watchdog running and exited. A task that is
meant to be hidden runs PowerShell under a headless conhost, which gives it a console with no window.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

# script -> the variable its New-ScheduledTaskAction executes
_HIDDEN_TASKS = {
    "Register-NovaLocalhostWatchdog.ps1": "$conhost",
    "Ensure-NovaMaintenanceTask.ps1": "$execute",
}


@pytest.mark.parametrize(("name", "var"), sorted(_HIDDEN_TASKS.items()))
def test_hidden_task_runs_under_a_headless_conhost(name: str, var: str) -> None:
    text = (_SCRIPTS / name).read_text(encoding="ascii")
    assert re.search(rf"\{var}\s*=\s*Join-Path \$env:SystemRoot 'System32\\conhost\.exe'", text), text
    actions = re.findall(r"New-ScheduledTaskAction\s+-Execute\s+(\S+)", text)
    assert actions == [var], actions
    assert "--headless" in text


def test_watchdog_action_still_names_the_watch_script() -> None:
    """engineRestart.mjs and Repair-NovaPriority.ps1 find the watchdog by its command line."""
    text = (_SCRIPTS / "Register-NovaLocalhostWatchdog.ps1").read_text(encoding="ascii")
    assert '-Argument "--headless `"$ps`" $arg"' in text
    assert "-File `\"$watch`\"" in text


def test_maintenance_check_expects_the_headless_action() -> None:
    """The startup check compares the saved task with the action it would register, so it does
    not re-register the task on every start."""
    text = (_SCRIPTS / "Ensure-NovaMaintenanceTask.ps1").read_text(encoding="ascii")
    assert "$actions[0].Execute -eq $execute" in text
    assert "$arguments = '--headless \"' + $powershell + '\"" in text
