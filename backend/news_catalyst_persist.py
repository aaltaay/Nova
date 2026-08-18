"""Dated JSON snapshot for news catalysts (mirrors gapper snapshots)."""
from __future__ import annotations

import json
import logging

from cache import _atomic_write, _dated_path, _today_et

logger = logging.getLogger(__name__)

_PREFIX = "news-catalysts"


def save_news_catalyst_snapshot(rows: list[dict], ts: float) -> None:
    try:
        payload = {"date": _today_et(), "ts": ts, "catalysts": rows}
        _atomic_write(_dated_path(_PREFIX, _today_et()), payload)
    except Exception:
        logger.warning(
            "news_catalyst_persist: save failed",
            exc_info=True,
        )


def load_news_catalyst_snapshot() -> tuple[list[dict], float]:
    try:
        path = _dated_path(_PREFIX, _today_et())
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != _today_et():
            return [], 0.0
        raw = data.get("catalysts", [])
        ts = float(data.get("ts", 0.0))
        return (raw if isinstance(raw, list) else []), ts
    except FileNotFoundError:
        return [], 0.0
    except Exception:
        logger.warning("news_catalyst_persist: load failed", exc_info=True)
        return [], 0.0
