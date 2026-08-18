"""CLI: WAL-safe copy of Nova's five local SQLite files.

Usage (from repo root):
  py -3 tools/backup_sqlite.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from archive.backup import backup_sqlite_once  # noqa: E402


def main() -> int:
    result = backup_sqlite_once()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
