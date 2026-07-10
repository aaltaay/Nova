"""
Resolve writable data paths for Nova (local, Railway, Electron desktop).

Prefer explicit env overrides so a frozen/desktop sidecar can write under
the user's AppData instead of Program Files.
"""
from __future__ import annotations

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent


def cache_dir() -> Path:
    raw = (
        os.environ.get("NOVA_CACHE_DIR")
        or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        or str(_BACKEND_DIR / ".cache")
    )
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    raw = os.environ.get("NOVA_LOG_DIR") or str(_BACKEND_DIR / "logs")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_file_path() -> Path:
    """Path used for load_dotenv / settings persistence."""
    override = os.environ.get("NOVA_ENV_PATH")
    if override:
        return Path(override)
    # Repo-root .env for local/Railway; next to backend when frozen without override.
    candidate = _REPO_ROOT / ".env"
    if candidate.is_file() or not getattr(__import__("sys"), "frozen", False):
        return candidate
    return Path(os.path.dirname(__import__("sys").executable)) / ".env"
