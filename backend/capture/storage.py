"""Capture storage location; never falls back into the checkout."""
import os
from pathlib import Path


def capture_root() -> Path:
    from capture.constants_capture import DEFAULT_SIM_CAPTURE_ROOT_WIN

    override = (os.environ.get("NOVA_SIM_CAPTURE_DIR") or "").strip()
    preferred = Path(DEFAULT_SIM_CAPTURE_ROOT_WIN)
    if override:
        root = Path(override)
    elif preferred.drive and Path(preferred.drive + "\\").exists():
        root = preferred
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Nova" / "sim_capture"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Nova" / "sim_capture"
    root.mkdir(parents=True, exist_ok=True)
    return root
