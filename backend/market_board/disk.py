"""The Market page's files under ``<cache_dir>/market-board/`` (ADR 053; shapes in architecture/schema/market-board.md).

Every file carries ``schema_version``; one of another version reads as absent (never migrated by guesswork), and a
write replaces the whole file atomically.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from constants_market_board import MARKET_SCHEMA_VERSION

logger = logging.getLogger(__name__)


def folder() -> Path:
    import paths

    path = paths.cache_dir() / "market-board"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read(name: str) -> dict[str, Any] | None:
    """The file's content, or ``None`` when it is missing, unreadable or of another schema version."""
    path = folder() / name
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("market_board: %s unreadable; treated as absent", path, exc_info=True)
        return None
    if not isinstance(data, dict) or data.get("schema_version") != MARKET_SCHEMA_VERSION:
        logger.warning("market_board: %s has schema_version %r; treated as absent", path,
                       data.get("schema_version") if isinstance(data, dict) else None)
        return None
    return data


def write(name: str, payload: dict[str, Any]) -> None:
    path = folder() / name
    body = {"schema_version": MARKET_SCHEMA_VERSION, **{k: v for k, v in payload.items() if k != "schema_version"}}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def remove(name: str) -> None:
    try:
        (folder() / name).unlink(missing_ok=True)
    except OSError:
        logger.warning("market_board: could not delete %s", name, exc_info=True)


def names(prefix: str) -> list[str]:
    return sorted(p.name for p in folder().glob(f"{prefix}*") if p.is_file())
