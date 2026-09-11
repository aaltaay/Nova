"""D-030 leftovers and api-console log rotation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.rotate_log_file import rotate_if_needed


def test_railway_toml_and_prebuild_removed() -> None:
    for rel in ("railway.toml", "backend/railway.toml", "frontend/railway.toml"):
        assert not (_ROOT / rel).exists(), rel
    assert not (_ROOT / "frontend" / "scripts" / "check-railway-api-base.mjs").exists()
    package = (_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    assert "check-railway-api-base" not in package
    assert '"prebuild"' not in package


@pytest.mark.parametrize(
    "rel",
    (
        "backend/paths.py",
        "backend/constants_scanner.py",
        "backend/constants_hod_momo.py",
    ),
)
def test_railway_volume_fallback_removed(rel: str) -> None:
    text = (_ROOT / rel).read_text(encoding="utf-8")
    assert "RAILWAY_VOLUME_MOUNT_PATH" not in text


def test_start_nova_api_rotates_console_log() -> None:
    text = (_ROOT / "scripts" / "Start-NovaApi.ps1").read_text(encoding="ascii")
    assert "rotate_log_file.py" in text
    assert "--path" in text


def test_rotate_skips_small_file(tmp_path: Path) -> None:
    log = tmp_path / "api-console.log"
    log.write_text("ok\n", encoding="utf-8")
    assert rotate_if_needed(log, max_bytes=1024, keep=2) is None
    assert log.is_file()


def test_rotate_renames_and_prunes(tmp_path: Path) -> None:
    live = tmp_path / "api-console.log"
    live.write_bytes(b"x" * 64)
    first = rotate_if_needed(live, max_bytes=8, keep=2, now=1_700_000_000)
    assert first is not None
    assert not live.exists()

    live.write_bytes(b"y" * 64)
    rotate_if_needed(live, max_bytes=8, keep=2, now=1_700_000_010)
    live.write_bytes(b"z" * 64)
    rotate_if_needed(live, max_bytes=8, keep=2, now=1_700_000_020)

    leftovers = sorted(p.name for p in tmp_path.glob("api-console-*.log"))
    assert len(leftovers) == 2
    assert first.name not in leftovers
