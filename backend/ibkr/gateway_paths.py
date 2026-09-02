"""Resolve IB Gateway exe / IBC launcher paths. Linux-safe Path construction."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from constants_ibkr import (
    IBKR_GATEWAY_EXE_DEFAULT,
    IBKR_GATEWAY_ROOT,
    IBKR_IBC_LAUNCHER_REL,
)


def _ibc_launcher() -> Path | None:
    candidate = Path.home() / IBKR_IBC_LAUNCHER_REL
    return candidate if candidate.is_file() else None


def _local_path(raw: str) -> Path:
    """Build a filesystem Path on the real host OS, not a mocked ``os.name``.

    Tests set ``os.name = "nt"`` so launch_or_focus_gateway takes the Windows
    branch. ``pathlib.Path`` also follows ``os.name``, so a naive ``Path(...)``
    tries ``WindowsPath`` and Linux CI dies.
    """
    if sys.platform != "win32":
        from pathlib import PosixPath

        return PosixPath(str(raw).replace("\\", "/"))
    return Path(raw)


def _resolve_gateway_exe() -> Path | None:
    override = (os.environ.get("IBKR_GATEWAY_EXE") or "").strip()
    if override:
        p = _local_path(override)
        return p if p.is_file() else None

    default = _local_path(IBKR_GATEWAY_EXE_DEFAULT)
    if default.is_file():
        return default
    renamed_default = default.with_name("ibgateway1.exe")
    if renamed_default.is_file():
        return renamed_default

    root = _local_path(IBKR_GATEWAY_ROOT)
    if not root.is_dir():
        return None
    found = sorted(
        list(root.glob("*/ibgateway.exe")) + list(root.glob("*/ibgateway1.exe")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return found[0] if found else None
