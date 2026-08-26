"""Operator-drawn chart lines, persisted per symbol (ADR 015).

Mirrors the ``large_cap_admin.py`` config pattern: a small JSON file carrying a
``schema_version``, refusing loud on an unknown version rather than silently
ignoring it (see ``.cursor/rules/persisted-state.mdc``).

Owner: this module (the only reader/writer of ``CHART_DRAWINGS_FILE``).
Invalidation trigger: an explicit ``PUT``/``DELETE`` only. Drawings are
deliberately session-independent -- a support level an operator marked last
Friday is still that level on Monday, so no session rollover, reconnect
generation, or scanner freeze stales them.

Anchor ``time`` is the canonical ET-shifted epoch second the frontend uses for
intraday bars (``tickerChartData.isoToEtTime``). Each chart pane snaps it to its
own nearest bar on load, so one stored anchor renders on every timeframe.
"""
from __future__ import annotations

import logging
import math

from constants import (
    CHART_DRAWINGS_MAX_ANCHORS,
    CHART_DRAWINGS_MAX_PER_SYMBOL,
    CHART_DRAWINGS_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

# symbol -> list of sanitized drawing dicts, in paint order.
_drawings: dict[str, list[dict]] = {}
_loaded = False


def _normalize_symbol(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol must not be empty")
    return sym


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _sanitize_anchor(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("each anchor must be an object with time and price")
    time = _finite(raw.get("time"))
    price = _finite(raw.get("price"))
    if time is None:
        raise ValueError("anchor time must be a finite number (ET epoch seconds)")
    if price is None:
        raise ValueError("anchor price must be a finite number")
    return {"time": time, "price": price}


def _sanitize_drawing(raw: object) -> dict:
    """Keep only the five fields ``SerializedDrawing`` defines -- never echo
    arbitrary client keys back onto disk."""
    if not isinstance(raw, dict):
        raise ValueError("each drawing must be an object")
    drawing_id = str(raw.get("id") or "").strip()
    drawing_type = str(raw.get("type") or "").strip()
    if not drawing_id:
        raise ValueError("drawing id must not be empty")
    if not drawing_type:
        raise ValueError("drawing type must not be empty")
    anchors_raw = raw.get("anchors")
    if not isinstance(anchors_raw, list) or not anchors_raw:
        raise ValueError(f"drawing {drawing_type} needs at least one anchor")
    if len(anchors_raw) > CHART_DRAWINGS_MAX_ANCHORS:
        raise ValueError(
            f"drawing {drawing_type} has {len(anchors_raw)} anchors "
            f"(max {CHART_DRAWINGS_MAX_ANCHORS})"
        )
    style = raw.get("style")
    options = raw.get("options")
    return {
        "id": drawing_id,
        "type": drawing_type,
        "anchors": [_sanitize_anchor(a) for a in anchors_raw],
        "style": dict(style) if isinstance(style, dict) else {},
        "options": dict(options) if isinstance(options, dict) else {},
    }


def _load() -> None:
    global _drawings, _loaded
    if _loaded:
        return
    _loaded = True
    import cache as _cache

    data = _cache.load_chart_drawings()
    if not data:
        return
    version = int(data.get("schema_version") or 0)
    if version != CHART_DRAWINGS_SCHEMA_VERSION:
        logger.warning(
            "chart_drawings: refusing file with unknown schema_version=%s "
            "(expected %s) -- starting empty, on-disk file left untouched",
            version, CHART_DRAWINGS_SCHEMA_VERSION,
        )
        return
    symbols = data.get("symbols")
    if not isinstance(symbols, dict):
        logger.warning("chart_drawings: 'symbols' is not an object -- starting empty")
        return
    loaded: dict[str, list[dict]] = {}
    for symbol, raw_list in symbols.items():
        if not isinstance(raw_list, list):
            continue
        try:
            sym = _normalize_symbol(str(symbol))
        except ValueError:
            continue
        kept: list[dict] = []
        for raw in raw_list[:CHART_DRAWINGS_MAX_PER_SYMBOL]:
            try:
                kept.append(_sanitize_drawing(raw))
            except ValueError as exc:
                # One bad row must not cost the operator every other level.
                logger.warning("chart_drawings: dropping bad %s drawing: %s", sym, exc)
        if kept:
            loaded[sym] = kept
    _drawings = loaded


def get_drawings(symbol: str) -> list[dict]:
    """Every stored drawing for *symbol* (empty list when none)."""
    _load()
    return [dict(d) for d in _drawings.get(_normalize_symbol(symbol), [])]


def replace_drawings(symbol: str, drawings: object) -> list[dict]:
    """Replace *symbol*'s whole list. Raises ``ValueError`` on bad input.

    Whole-list replace (not per-drawing CRUD) because the client's source of
    truth is ``DrawingManager.exportDrawings()`` -- a full snapshot.
    """
    _load()
    sym = _normalize_symbol(symbol)
    if not isinstance(drawings, list):
        raise ValueError("drawings must be a list")
    if len(drawings) > CHART_DRAWINGS_MAX_PER_SYMBOL:
        raise ValueError(
            f"{len(drawings)} drawings exceeds the {CHART_DRAWINGS_MAX_PER_SYMBOL} "
            f"per-symbol cap"
        )
    sanitized = [_sanitize_drawing(d) for d in drawings]
    if sanitized:
        _drawings[sym] = sanitized
    else:
        _drawings.pop(sym, None)
    _save()
    return [dict(d) for d in sanitized]


def clear_drawings(symbol: str) -> None:
    """Drop every drawing for *symbol*."""
    _load()
    sym = _normalize_symbol(symbol)
    if _drawings.pop(sym, None) is not None:
        _save()


def _save() -> None:
    import cache as _cache

    payload = {
        "schema_version": CHART_DRAWINGS_SCHEMA_VERSION,
        "symbols": _drawings,
    }
    _cache.save_chart_drawings(payload)


def reset_for_testing() -> None:
    """Test-only: force a clean in-memory state without touching disk."""
    global _drawings, _loaded
    _drawings = {}
    _loaded = True
