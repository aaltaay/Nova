"""Resolve IB Gateway exe / IBC launcher paths. Linux-safe Path construction."""
from __future__ import annotations

import os
from pathlib import Path

from constants_ibkr import (
    IBKR_GATEWAY_EXE_DEFAULT,
    IBKR_GATEWAY_ROOT,
)
from paths import host_path as _local_path


def _ibc_launcher() -> Path | None:
    # IBKR_IBC_LAUNCHER_REL is a Windows relative string. Joining it onto
    # Path.home() on POSIX makes one filename (".nova\\ibc\\..."). Use parts.
    candidate = Path.home() / ".nova" / "ibc" / "start_gateway.ps1"
    return candidate if candidate.is_file() else None


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
