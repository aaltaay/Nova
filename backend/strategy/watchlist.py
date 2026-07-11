"""
Watchlist — Five Pillars scoring + composite ranking, signal-only.

Takes the current scanner candidates (gappers/gainers), scores each against
the Five Pillars, and layers a weighted composite score on top so the UI can
show one ranked table instead of a flat list. Symbols that pass all 5 pillars
always rank above ones that don't; the composite score only orders within
each group.

Read-only: never fetches data itself (caller passes candidates), never
places orders. See five_pillars.py for pillar semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from constants import (
    FIVE_PILLARS_MAX_FLOAT_SHARES,
    WATCHLIST_CATALYST_FRESH_MINUTES,
    WATCHLIST_CATALYST_STALE_MINUTES,
    WATCHLIST_CHANGE_PCT_SCORE_CAP,
    WATCHLIST_MAX_ROWS,
    WATCHLIST_REL_VOLUME_SCORE_CAP,
    WATCHLIST_WEIGHT_CATALYST,
    WATCHLIST_WEIGHT_CHANGE_PCT,
    WATCHLIST_WEIGHT_FLOAT,
    WATCHLIST_WEIGHT_REL_VOLUME,
)
from strategy.five_pillars import FivePillarsResult, evaluate_five_pillars


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    five_pillars: FivePillarsResult
    composite_score: float
    sub_scores: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "composite_score": round(self.composite_score, 1),
            "sub_scores": {k: round(v, 1) for k, v in self.sub_scores.items()},
            "five_pillars": self.five_pillars.to_dict(),
        }


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _change_pct_score(change_pct: float | None) -> float:
    if change_pct is None:
        return 0.0
    pct = change_pct * 100 if abs(change_pct) <= 1.0 else change_pct
    return _clamp(pct / WATCHLIST_CHANGE_PCT_SCORE_CAP * 100)


def _rel_volume_score(rel_volume: float | None) -> float:
    if rel_volume is None:
        return 0.0
    return _clamp(rel_volume / WATCHLIST_REL_VOLUME_SCORE_CAP * 100)


def _float_score(float_shares: float | None) -> float:
    if float_shares is None:
        return 0.0
    return _clamp((1 - float_shares / FIVE_PILLARS_MAX_FLOAT_SHARES) * 100)


def _catalyst_score(has_news: bool | None, newest_headline_at: str | None) -> float:
    if not has_news:
        return 0.0
    if not newest_headline_at:
        # News flagged but no timestamp to age it — treat as fully fresh.
        return 100.0
    try:
        published = datetime.fromisoformat(str(newest_headline_at).replace("Z", "+00:00"))
    except ValueError:
        return 100.0
    age_minutes = (datetime.now(timezone.utc) - published).total_seconds() / 60.0
    if age_minutes <= WATCHLIST_CATALYST_FRESH_MINUTES:
        return 100.0
    if age_minutes >= WATCHLIST_CATALYST_STALE_MINUTES:
        return 0.0
    span = WATCHLIST_CATALYST_STALE_MINUTES - WATCHLIST_CATALYST_FRESH_MINUTES
    return _clamp(100.0 * (1 - (age_minutes - WATCHLIST_CATALYST_FRESH_MINUTES) / span))


def score_watchlist_entry(candidate: dict) -> WatchlistEntry:
    """Score one candidate: Five Pillars pass/fail + weighted composite score."""
    symbol = candidate.get("symbol", "?")
    pillars = evaluate_five_pillars(candidate)

    change_pct = candidate.get("change_pct", candidate.get("gap_percent"))
    sub_scores = {
        "change_pct": _change_pct_score(change_pct),
        "relative_volume": _rel_volume_score(candidate.get("rel_volume")),
        "float": _float_score(candidate.get("float", candidate.get("float_shares"))),
        "catalyst": _catalyst_score(candidate.get("has_news"), candidate.get("newest_headline_at")),
    }
    composite = (
        sub_scores["change_pct"] * WATCHLIST_WEIGHT_CHANGE_PCT
        + sub_scores["relative_volume"] * WATCHLIST_WEIGHT_REL_VOLUME
        + sub_scores["float"] * WATCHLIST_WEIGHT_FLOAT
        + sub_scores["catalyst"] * WATCHLIST_WEIGHT_CATALYST
    )
    return WatchlistEntry(symbol=symbol, five_pillars=pillars, composite_score=composite, sub_scores=sub_scores)


def build_watchlist(candidates: list[dict], limit: int = WATCHLIST_MAX_ROWS) -> list[WatchlistEntry]:
    """Score and rank every candidate: all-pillars-pass first, then composite score."""
    entries = [score_watchlist_entry(c) for c in candidates]
    entries.sort(key=lambda e: (e.five_pillars.all_pass, e.composite_score), reverse=True)
    return entries[:limit]
