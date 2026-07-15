"""
Nova API process entry (local uvicorn + PyInstaller sidecar).

Usage:
  py -3 run_api.py
  nova-api.exe   # frozen

Env vars:
  NOVA_API_HOST    -- bind host (default 127.0.0.1)
  NOVA_API_PORT    -- bind port (default 8000)
  NOVA_API_RELOAD  -- "true" to enable uvicorn --reload for local dev
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def _force_utf8_io() -> None:
    """
    Force UTF-8 stdio so log messages containing non-ASCII characters (e.g.
    arrows, emoji) never crash the process on Windows, whose console default
    encoding (cp1252) cannot represent them. See PROBLEM_LOG.md 2026-07-10
    "UnicodeEncodeError during logging on Windows console".

    Two mechanisms are needed:
    - `os.environ["PYTHONIOENCODING"]` so any child interpreter spawned later
      (uvicorn --reload uses `multiprocessing.spawn` on Windows, which starts
      a brand-new interpreter that reads this env var at startup rather than
      inheriting our in-process stream state) also gets UTF-8 stdio.
    - `sys.stdout/stderr.reconfigure(...)` so *this* process is fixed too,
      for the no-reload path where uvicorn runs in-process.
    """
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:backslashreplace")
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                logger.debug("run_api: could not reconfigure %s to utf-8", stream_name, exc_info=True)


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
    _force_utf8_io()
    _prepare_sys_path()
    import uvicorn

    host = os.environ.get("NOVA_API_HOST", "127.0.0.1")
    port = int(os.environ.get("NOVA_API_PORT", "8000"))
    reload = os.environ.get("NOVA_API_RELOAD", "false").lower() in ("1", "true", "yes")

    if reload:
        # uvicorn's file-watcher needs an import string (not an app object) to
        # be able to restart the process on code changes.
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=True,
            reload_excludes=["logs/*", ".cache/*", "dist/*"],
            log_level="info",
        )
    else:
        # Force-import so PyInstaller bundles the FastAPI app modules.
        import main as app_main  # noqa: F401
        uvicorn.run(
            app_main.app,
            host=host,
            port=port,
            reload=False,
            log_level="info",
        )


if __name__ == "__main__":
    main()
