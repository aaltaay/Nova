"""Start-NovaApi.ps1 must default to a stable (no WatchFiles) process."""
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "Start-NovaApi.ps1"


def test_start_nova_api_defaults_reload_off() -> None:
    text = _SCRIPT.read_text(encoding="ascii")
    assert "[switch]$Reload" in text
    assert '$env:NOVA_API_RELOAD = "0"' in text
    # Unconditional force-on is the 2026-08-28 morning regression.
    assert "$env:NOVA_API_RELOAD = \"1\"" not in text.split("if ($Reload)")[0]


def test_start_nova_api_reload_is_opt_in_only() -> None:
    text = _SCRIPT.read_text(encoding="ascii")
    assert "if ($Reload)" in text
    after = text.split("if ($Reload)", 1)[1]
    assert '$env:NOVA_API_RELOAD = "1"' in after
