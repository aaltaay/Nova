"""Local Gateway jts.ini flags. Never logs secrets or 2FA device hashes."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from constants_ibkr import IBKR_JTS_INI_PATHS

logger = logging.getLogger(__name__)


def clear_restart_token() -> None:
    """Drop Restart=OK so the next login can show the 2FA code box."""
    for raw in IBKR_JTS_INI_PATHS:
        path = Path(raw)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(r"^Restart=.*$", re.MULTILINE)
        if not pattern.search(text):
            continue
        path.write_text(pattern.sub("Restart=", text, count=1), encoding="utf-8")
        logger.info("IBKR: cleared Restart=OK in %s", path)
