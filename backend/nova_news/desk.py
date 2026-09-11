"""Assemble the Nova News desk view.

Owner of ``nova-news-desk.json`` (persisted-state.mdc).
Invalidation trigger: TTL expiry or ``NOVA_NEWS_DESK_SCHEMA_VERSION`` bump.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from constants import (
    NOVA_NEWS_CRITICALITY_ORDER,
    NOVA_NEWS_DESK_CACHE_FILENAME,
    NOVA_NEWS_DESK_MAX_STORIES,
    NOVA_NEWS_DESK_SCHEMA_VERSION,
    NOVA_NEWS_DESK_TTL_SEC,
)
from nova_news.models import ProviderResult
from nova_news.normalize import stories_from_providers
from nova_news.providers import fetch_all_providers
from paths import cache_dir

logger = logging.getLogger(__name__)

_cache_view: dict | None = None
_cache_ts: float = 0.0


def _cache_path() -> Path:
    return cache_dir() / NOVA_NEWS_DESK_CACHE_FILENAME


def _empty_columns() -> dict[str, list]:
    return {key: [] for key in NOVA_NEWS_CRITICALITY_ORDER}


def _counts_for(stories: list) -> dict[str, int]:
    counts = {key: 0 for key in NOVA_NEWS_CRITICALITY_ORDER}
    counts["total"] = len(stories)
    for story in stories:
        band = story.criticality if story.criticality in counts else "background"
        counts[band] = counts.get(band, 0) + 1
    return counts


def _public_sources(sources: list[ProviderResult], stories: list) -> list[dict]:
    admitted: dict[str, int] = {}
    for story in stories:
        admitted[story.provider] = admitted.get(story.provider, 0) + 1
    public = []
    for src in sources:
        row = src.to_public()
        if src.ok:
            row["count"] = admitted.get(src.id, 0)
        public.append(row)
    return public


def _view(
    stories: list,
    sources: list[ProviderResult],
    as_of: float,
    error: str | None,
) -> dict:
    capped = stories[:NOVA_NEWS_DESK_MAX_STORIES]
    columns = _empty_columns()
    for story in capped:
        band = story.criticality if story.criticality in columns else "background"
        columns[band].append(story.to_dict())
    return {
        "schema_version": NOVA_NEWS_DESK_SCHEMA_VERSION,
        "as_of": as_of,
        "error": error,
        "sources": _public_sources(sources, capped),
        "counts": _counts_for(capped),
        "columns": columns,
        "stories": [s.to_dict() for s in capped],
    }


def _load_disk() -> tuple[dict | None, float]:
    try:
        with _cache_path().open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, 0.0
    except Exception:
        logger.warning("nova_news: disk snapshot unreadable", exc_info=True)
        return None, 0.0
    if int(data.get("schema_version") or 0) != NOVA_NEWS_DESK_SCHEMA_VERSION:
        logger.warning(
            "nova_news: refusing disk snapshot schema_version=%s",
            data.get("schema_version"),
        )
        return None, 0.0
    return data, float(data.get("as_of") or 0.0)


def _save_disk(view: dict) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(view), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        logger.warning("nova_news: failed to persist snapshot", exc_info=True)


def _ensure_loaded() -> None:
    global _cache_view, _cache_ts
    if _cache_view is not None:
        return
    view, ts = _load_disk()
    _cache_view = view
    _cache_ts = ts


def _loud_error(results: list[ProviderResult]) -> str:
    parts = [f"{r.label}: {r.error}" for r in results if r.error]
    if not parts:
        return "Nova News could not load any headlines."
    return "Nova News sources failed -- " + " | ".join(parts[:4])


def build_desk(*, force: bool = False, now: datetime | None = None) -> dict:
    """Return the desk payload. Empty + error when every source is down."""
    global _cache_view, _cache_ts
    _ensure_loaded()
    wall = time.time()
    fresh = _cache_view is not None and (wall - _cache_ts) < NOVA_NEWS_DESK_TTL_SEC
    if fresh and not force:
        return dict(_cache_view)

    now = now or datetime.now(timezone.utc)
    results = fetch_all_providers()
    stories = stories_from_providers(results, now=now)
    any_ok = any(r.ok for r in results)

    if not any_ok and not stories:
        if _cache_view:
            logger.warning("nova_news: all sources failed -- serving stale snapshot")
            stale = dict(_cache_view)
            stale["error"] = None
            return stale
        view = _view([], results, 0.0, _loud_error(results))
        return view

    view = _view(stories, results, wall, None)
    _cache_view = view
    _cache_ts = wall
    _save_disk(view)
    return view


def reset_for_testing() -> None:
    global _cache_view, _cache_ts
    _cache_view = None
    _cache_ts = 0.0
