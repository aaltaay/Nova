"""News impact helper functions and classification constants (ADR 004)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from constants import (
    NEWS_IMPACT_AGING_HOURS,
    NEWS_IMPACT_ATTENTION_RVOL,
    NEWS_IMPACT_CONFIDENCE_CEILING,
    NEWS_IMPACT_CONFIDENCE_FLOOR,
    NEWS_IMPACT_FRESH_HOURS,
    NEWS_IMPACT_L2_IMBALANCE_MIN,
    NEWS_IMPACT_MILD_MOVE_PCT,
    NEWS_IMPACT_MULTI_SOURCE_CONFIRM,
    NEWS_IMPACT_RULE_VERSION,
    NEWS_IMPACT_STALE_HOURS,
    NEWS_IMPACT_STRONG_MOVE_PCT,
)

IMPACT_CLASSES = ("moved_price", "attention_only", "no_effect", "insufficient_data")
AGE_BUCKETS = ("fresh", "aging", "stale", "expired", "unknown")
PRICE_REACTIONS = ("strong", "mild", "flat", "unknown")
L2_REACTIONS = ("reacting", "quiet", "insufficient_data")
ATTENTION_STATES = ("elevated", "normal", "unknown")


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def age_hours(newest_at: str | None, now: datetime | None = None) -> float | None:
    published = parse_iso(newest_at)
    if published is None:
        return None
    now = now or datetime.now(timezone.utc)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0.0, (now - published).total_seconds() / 3600.0)


def age_bucket(age_hours_val: float | None) -> str:
    if age_hours_val is None:
        return "unknown"
    if age_hours_val <= NEWS_IMPACT_FRESH_HOURS:
        return "fresh"
    if age_hours_val <= NEWS_IMPACT_AGING_HOURS:
        return "aging"
    if age_hours_val <= NEWS_IMPACT_STALE_HOURS:
        return "stale"
    return "expired"


def gap_pct_points(gap_percent: float | None) -> float | None:
    """Normalize gap to percentage points. Accepts fraction (0.12) or points (12)."""
    if gap_percent is None:
        return None
    try:
        raw = float(gap_percent)
    except (TypeError, ValueError):
        return None
    # Heuristic: values with |x| ≤ 1.5 are treated as fractions (150% max as fraction).
    if abs(raw) <= 1.5:
        return abs(raw) * 100.0
    return abs(raw)


def price_reaction(gap_pct: float | None) -> str:
    if gap_pct is None:
        return "unknown"
    if gap_pct >= NEWS_IMPACT_STRONG_MOVE_PCT:
        return "strong"
    if gap_pct >= NEWS_IMPACT_MILD_MOVE_PCT:
        return "mild"
    return "flat"


def attention_state(rel_volume: float | None) -> str:
    if rel_volume is None:
        return "unknown"
    try:
        return "elevated" if float(rel_volume) >= NEWS_IMPACT_ATTENTION_RVOL else "normal"
    except (TypeError, ValueError):
        return "unknown"


def l2_reaction(l2_features: dict | None) -> str:
    if not l2_features:
        return "insufficient_data"
    if l2_features.get("bid_heavy") is True:
        return "reacting"
    imb = l2_features.get("imbalance")
    try:
        if imb is not None and abs(float(imb)) >= NEWS_IMPACT_L2_IMBALANCE_MIN:
            return "reacting"
    except (TypeError, ValueError):
        imb = None
    # Explicit quiet only when we actually computed features.
    if "imbalance" in l2_features or "bid_heavy" in l2_features:
        return "quiet"
    return "insufficient_data"


def clamp_confidence(raw: float) -> float:
    return round(
        max(NEWS_IMPACT_CONFIDENCE_FLOOR, min(NEWS_IMPACT_CONFIDENCE_CEILING, raw)),
        3,
    )


def factors_snapshot() -> dict[str, Any]:
    """Expose every tunable used by this rule version (UI / debugging)."""
    return {
        "rule_version": NEWS_IMPACT_RULE_VERSION,
        "fresh_hours": NEWS_IMPACT_FRESH_HOURS,
        "aging_hours": NEWS_IMPACT_AGING_HOURS,
        "stale_hours": NEWS_IMPACT_STALE_HOURS,
        "strong_move_pct": NEWS_IMPACT_STRONG_MOVE_PCT,
        "mild_move_pct": NEWS_IMPACT_MILD_MOVE_PCT,
        "attention_rvol": NEWS_IMPACT_ATTENTION_RVOL,
        "l2_imbalance_min": NEWS_IMPACT_L2_IMBALANCE_MIN,
        "multi_source_confirm": NEWS_IMPACT_MULTI_SOURCE_CONFIRM,
        "confidence_floor": NEWS_IMPACT_CONFIDENCE_FLOOR,
        "confidence_ceiling": NEWS_IMPACT_CONFIDENCE_CEILING,
    }
