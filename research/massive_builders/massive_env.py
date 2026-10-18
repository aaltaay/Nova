"""Where the Massive builders read and write, and their credentials, from the environment.

``NOVA_MARKET_DATA_DIR`` -- the Massive files, the derived products, the logs and state files (default
``E:\\Nova\\massive``, the convention of ``research/market_reads/roots.py``).
``NOVA_EDGE_LAB_DIR`` -- the research lab whose own ticker lists join each day's movers (default
``F:\\Nova\\private\\edge-lab``; absent folders are simply skipped).
``NOVA_ENV_PATH`` -- the ``.env`` holding the Massive keys (default the repo's ``.env``). A process environment
variable of the same name wins over the file. Values are returned, never printed or logged.

Nothing here touches the disk at import.
"""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("NOVA_MARKET_DATA_DIR") or r"E:\Nova\massive")
EDGE_LAB = Path(os.environ.get("NOVA_EDGE_LAB_DIR") or r"F:\Nova\private\edge-lab")
TMP = ROOT / "_tmp"                      # scratch: partial downloads and DuckDB spill folders
NY = ZoneInfo("America/New_York")
KEYS = ("MASSIVE_S3_ACCESS_KEY_ID", "MASSIVE_S3_SECRET_ACCESS_KEY", "MASSIVE_S3_ENDPOINT", "MASSIVE_API_KEY",
        "POLYGON_API_KEY")


def env_file() -> Path:
    return Path(os.environ.get("NOVA_ENV_PATH") or REPO / ".env")


def env_values() -> dict[str, str]:
    """The ``.env`` file's KEY=value pairs (a missing file is empty), with the process environment's ``KEYS`` on top."""
    vals: dict[str, str] = {}
    try:
        text = env_file().read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    for line in text.splitlines():
        k, _, v = line.strip().partition("=")
        vals[k.strip()] = v.strip().strip('"').strip("'")
    vals.update({k: os.environ[k] for k in KEYS if os.environ.get(k)})
    return vals
