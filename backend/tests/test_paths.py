"""Host-OS path construction -- ignore a mocked os.name."""
from __future__ import annotations

import os
import sys
from pathlib import Path, PosixPath


def test_cache_dir_is_host_path_when_os_name_is_nt(monkeypatch, tmp_path: Path):
    from paths import cache_dir, host_path

    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path / "bot-cache"))
    monkeypatch.setattr(os, "name", "nt")
    path = cache_dir()
    assert path.exists()
    if sys.platform != "win32":
        assert isinstance(path, PosixPath)
        assert isinstance(path / "bot-session.json", PosixPath)
    assert isinstance(host_path(str(tmp_path / "x")), Path)
