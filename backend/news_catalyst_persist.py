"""Dated JSON snapshot for news catalysts (mirrors gapper snapshots)."""
from __future__ import annotations

import logging

from cache import _read_dated_json, _today_et, _write_dated

logger = logging.getLogger(__name__)

_PREFIX = "news-catalysts"


def save_news_catalyst_snapshot(rows: list[dict], ts: float) -> None:
    try:
        _write_dated(
            _PREFIX,
            _today_et(),
            {"date": _today_et(), "ts": ts, "catalysts": rows},
        )
    except Exception:
        logger.warning(
            "news_catalyst_persist: save failed",
            exc_info=True,
        )


def load_news_catalyst_snapshot() -> tuple[list[dict], float]:
    try:
        data = _read_dated_json(_PREFIX, _today_et())
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
