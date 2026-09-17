"""
Resolve writable data paths for Nova (local / Electron desktop).

Prefer explicit env overrides so a frozen/desktop sidecar can write under
the user's AppData instead of Program Files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent


def host_path(raw: str | os.PathLike[str]) -> Path:
    """Filesystem Path on the real host OS, not a mocked ``os.name``.

    Gateway tests set ``os.name = "nt"`` so launch_or_focus_gateway takes
    the Windows branch. ``pathlib.Path`` follows that mock: ``Path(raw)``
    can mint a ``WindowsPath``, then ``path / name`` calls
    ``WindowsPath.__new__`` (bound at import on Linux) and CI dies.
    """
    if sys.platform != "win32":
        from pathlib import PosixPath

        return PosixPath(str(raw).replace("\\", "/"))
    return Path(raw)


def cache_dir() -> Path:
    raw = (
        os.environ.get("NOVA_CACHE_DIR")
        or str(_BACKEND_DIR / ".cache")
    )
    path = host_path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    raw = os.environ.get("NOVA_LOG_DIR") or str(_BACKEND_DIR / "logs")
    path = host_path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_file_path() -> Path:
    """Path used for load_dotenv / settings persistence."""
    override = os.environ.get("NOVA_ENV_PATH")
    if override:
        return host_path(override)
    # Repo-root .env for local; next to backend when frozen without override.
    candidate = _REPO_ROOT / ".env"
    if candidate.is_file() or not getattr(sys, "frozen", False):
        return candidate
    return host_path(os.path.dirname(sys.executable)) / ".env"
