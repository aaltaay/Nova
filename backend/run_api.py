"""
Nova API process entry (local uvicorn + PyInstaller sidecar).

Usage:
  py -3 run_api.py
  nova-api.exe   # frozen
"""
from __future__ import annotations

import os
import sys


def _prepare_sys_path() -> None:
    if getattr(sys, "frozen", False):
        # onedir: modules live next to the executable / in _internal
        base = os.path.dirname(sys.executable)
        if base not in sys.path:
            sys.path.insert(0, base)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        os.chdir(here)


def main() -> None:
    _prepare_sys_path()
    # Force-import so PyInstaller bundles the FastAPI app modules.
    import main as app_main  # noqa: F401
    import uvicorn

    host = os.environ.get("NOVA_API_HOST", "127.0.0.1")
    port = int(os.environ.get("NOVA_API_PORT", "8000"))
    uvicorn.run(
        app_main.app,
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
