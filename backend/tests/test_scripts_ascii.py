"""Guard: Task Scheduler (powershell 5.1) corrupts non-ASCII .ps1 without BOM.

See PROBLEM_LOG 2026-07-30 -- morning empty-scanners wedge / daily-start
encoding: UTF-8 em dashes / ellipses turned the recycle branch into a garbled
string so a wedged API on port 8000 survived the 6 AM task.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
# Scripts launched by NovaDailyStart / Run Nova (must stay ASCII-clean).
_CRITICAL_PS1 = (
    "Start-NovaDaily.ps1",
    "Start-NovaApi.ps1",
    "Stop-NovaPorts.ps1",
    "Start-NovaUi.ps1",
    "Start-NovaDevDesktop.ps1",
)


@pytest.mark.parametrize("name", _CRITICAL_PS1)
def test_critical_ps1_is_ascii_only(name: str) -> None:
    path = _SCRIPTS / name
    assert path.is_file(), f"missing script: {path}"
    raw = path.read_bytes()
    # Reject UTF-8 BOM too -- Task Scheduler + some editors then disagree
    # about the encoding of the rest of the file.
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{name} has a UTF-8 BOM"
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        pytest.fail(f"{name} contains non-ASCII at byte {exc.start}: {exc.reason}")
    # Belt-and-suspenders: common punctuation that previously broke recycle.
    for bad in ("\u2014", "\u2013", "\u2026", "\u2018", "\u2019", "\u201c", "\u201d"):
        assert bad not in text, f"{name} contains forbidden char U+{ord(bad):04X}"
