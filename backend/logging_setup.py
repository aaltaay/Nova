"""
Root logging configuration: console + persistent rotating file.

Extracted out of main.py (see backend-modularity rule) so bootstrap plumbing
doesn't keep growing an already-over-limit file.

Without a console handler, every logger.info/warning/error call in modules
like ibkr/depth.py is only ever visible by opening logs/blast.log after the
fact — during live debugging that turns a 30-second "read the terminal"
check into a "grep a multi-MB log file" detour. See PROBLEM_LOG.md
2026-07-13, "Level 2 depth ladder flickered..." — the fix was found quickly
once blast.log was read, but reaching for the log file at all instead of
just watching the running terminal cost real time.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from ibkr.log_filters import install_ibkr_log_filters
from paths import log_dir as _nova_log_dir

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

logger = logging.getLogger(__name__)


def _force_utf8_console() -> None:
    """Non-ASCII log characters (arrows, emoji) crash on Windows' default
    cp1252 console encoding. run_api.py already does this for the
    entrypoint process, but main.py is also imported directly by
    `uvicorn main:app` during local dev, which skips that entrypoint."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                logger.debug("logging_setup: could not reconfigure %s to utf-8", stream_name, exc_info=True)


def configure_logging() -> None:
    _force_utf8_console()
    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(str(_nova_log_dir()), "blast.log"),
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
        errors="backslashreplace",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)

    # Keep ib_async's own noisy internal loggers from spamming Sentry with
    # known-benign IBKR conditions (see ibkr/log_filters.py) — local logs are
    # unaffected, they just see the downgraded WARNING level instead of ERROR.
    install_ibkr_log_filters()
