"""Start-NovaDevDesktop.ps1 Lock A contracts -- attach, never recycle :8000."""
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "Start-NovaDevDesktop.ps1"
_SIDECAR = _REPO / "frontend" / "electron" / "sidecar.mjs"
_MAIN = _REPO / "frontend" / "electron" / "main.mjs"


def test_dev_desktop_script_exists_ascii() -> None:
    raw = _SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("ascii")


def test_dev_desktop_lock_a_never_stop_ports() -> None:
    text = _SCRIPT.read_text(encoding="ascii")
    assert "never calls Stop-NovaPorts" in text
    assert "& $stopScript" not in text
    assert 'Join-Path $RepoRoot "scripts\\Stop-NovaPorts.ps1"' not in text
    assert "Start-NovaApi.ps1" in text
    assert 'Join-Path $RepoRoot "scripts\\Start-NovaApi.ps1"' not in text


def test_dev_desktop_requires_health_200_and_skip_sidecar() -> None:
    text = _SCRIPT.read_text(encoding="ascii")
    assert "Test-ApiHealth200" in text
    assert "StatusCode -eq 200" in text
    assert "NOVA_SKIP_API_SIDECAR" in text
    assert '$env:NOVA_SKIP_API_SIDECAR = "1"' in text
    assert '$env:NOVA_VITE_URL = "http://127.0.0.1:5173"' in text
    assert "Start-NovaUi.ps1" in text
    assert "[switch]$PullMaster" in text
    assert "exit 1" in text
    assert "reload the api" in text.lower()


def test_electron_honors_skip_api_sidecar() -> None:
    sidecar = _SIDECAR.read_text(encoding="utf-8")
    main = _MAIN.read_text(encoding="utf-8")
    assert "skipApiSidecar" in sidecar
    assert "NOVA_SKIP_API_SIDECAR" in sidecar
    assert "skipApiSidecar" in main
    assert "stopExternalListener" in sidecar
    # restart / stop-ports must consult the skip flag.
    restart_idx = sidecar.index("export function restartApiSidecar")
    restart_fn = sidecar[restart_idx : restart_idx + 600]
    assert "skipApiSidecar()" in restart_fn
    stop_idx = sidecar.index("function stopExternalListener")
    stop_fn = sidecar[stop_idx : stop_idx + 400]
    assert "skipApiSidecar()" in stop_fn
