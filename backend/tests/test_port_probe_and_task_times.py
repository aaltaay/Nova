"""The morning check's port test and the daily tasks' start times (#14).

2026-10-30 to 11-15: ``NovaMorningCheck`` failed ``gateway_port`` every morning while Nova was
connected through IB Gateway's 4001 -- Windows listed no listener for a port that accepted
connections. And from 2026-11-01 the daily tasks ran an hour early: their start times had been
saved with the summer UTC offset, so they did not follow the clock change.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "scripts"
_POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
_windows = pytest.mark.skipif(
    sys.platform != "win32" or not _POWERSHELL.exists(), reason="Windows PowerShell 5.1"
)


def _run(tmp_path: Path, body: str) -> dict:
    script = tmp_path / "check.ps1"
    script.write_text(textwrap.dedent(body), encoding="ascii")
    done = subprocess.run(
        [str(_POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_no_script_trusts_the_listing_alone() -> None:
    """Only the probe (and the port stopper, which needs the owning process) reads the listing."""
    allowed = {"NovaPortProbe.ps1", "Stop-NovaPorts.ps1"}
    for path in sorted(_SCRIPTS.glob("*.ps1")):
        if path.name in allowed:
            continue
        code = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
        )
        assert "-State Listen" not in code, f"{path.name} decides a port is closed from the listing alone"


def test_no_script_writes_a_daily_start_with_an_offset() -> None:
    for path in sorted(_SCRIPTS.glob("*.ps1")):
        if path.name == "NovaTaskTrigger.ps1":
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"New-ScheduledTaskTrigger\s+-Daily", text), (
            f"{path.name}: use New-NovaDailyTrigger, its start follows daylight saving"
        )


def test_the_maintenance_task_is_reinstalled_when_its_start_carries_an_offset() -> None:
    text = (_SCRIPTS / "Ensure-NovaMaintenanceTask.ps1").read_text(encoding="ascii")
    assert "(Test-NovaTriggerFollowsClock $triggers[0])" in text


@_windows
def test_a_connection_proves_a_port_the_listing_misses(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        open_port = server.getsockname()[1]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as spare:
            spare.bind(("127.0.0.1", 0))
            closed_port = spare.getsockname()[1]
        seen = _run(
            tmp_path,
            f"""
            . '{_SCRIPTS / "NovaPortProbe.ps1"}'
            function Test-NovaPortListed([int]$Port) {{ return $false }}   # the listing shows nothing
            @{{
                open = Get-NovaPortProof {open_port}
                closed = Get-NovaPortProof {closed_port}
                closed_open = Test-NovaPortOpen {closed_port}
            }} | ConvertTo-Json -Compress
            """,
        )
    assert seen == {"open": "connect", "closed": "", "closed_open": False}


@_windows
def test_a_listed_port_is_believed_as_it_is(tmp_path: Path) -> None:
    """No connection is opened to a port Windows lists. (The listing itself is stubbed: on the
    desk's Windows build it shows no state for a loopback listener, which is the fault.)"""
    seen = _run(
        tmp_path,
        f"""
        . '{_SCRIPTS / "NovaPortProbe.ps1"}'
        function Test-NovaPortListed([int]$Port) {{ return $true }}
        function Test-NovaPortConnect([int]$Port) {{ throw 'a listed port was connected to' }}
        @{{ proof = Get-NovaPortProof 4001; open = Test-NovaPortOpen 4001 }} | ConvertTo-Json -Compress
        """,
    )
    assert seen == {"proof": "listing", "open": True}


@_windows
def test_a_daily_start_is_local_time_with_no_offset(tmp_path: Path) -> None:
    seen = _run(
        tmp_path,
        f"""
        . '{_SCRIPTS / "NovaTaskTrigger.ps1"}'
        $new = New-NovaDailyTrigger (Get-Date '03:40')
        $old = New-ScheduledTaskTrigger -Daily -At (Get-Date '03:40')
        @{{
            start = [string]$new.StartBoundary
            interval = [int]$new.DaysInterval
            follows = [bool](Test-NovaTriggerFollowsClock $new)
            saved = [bool](Test-NovaTriggerFollowsClock ([pscustomobject]@{{ StartBoundary = '2026-08-18T02:40:00-05:00' }}))
            utc = [bool](Test-NovaTriggerFollowsClock ([pscustomobject]@{{ StartBoundary = '2026-08-18T07:40:00Z' }}))
            stock = [bool](Test-NovaTriggerFollowsClock $old)
        }} | ConvertTo-Json -Compress
        """,
    )
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T03:40:00", seen["start"]), seen
    assert seen["interval"] == 1 and seen["follows"] is True
    assert seen["saved"] is False and seen["utc"] is False
    assert seen["stock"] is False        # what the installer used to write
