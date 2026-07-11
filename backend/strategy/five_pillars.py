"""
Five Pillars of Stock Selection — signal-only scoring.

Scores a candidate dict (same shape as a gapper/gainer cache row: symbol, price,
change_pct, rel_volume, has_news, float, ...) against five independent criteria.
A stock only gets the "all pillars" checkmark when every pillar passes.

This module is read-only: it never fetches data, never places orders, and never
mutates its input. It is pure evaluation logic so it can be unit tested with
mock data and reused by any future UI or route.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from constants import (
    FIVE_PILLARS_MAX_FLOAT_SHARES,
    FIVE_PILLARS_MAX_PRICE,
    FIVE_PILLARS_MIN_CHANGE_PCT,
    FIVE_PILLARS_MIN_PRICE,
    FIVE_PILLARS_MIN_REL_VOLUME,
)

PILLAR_NAMES: tuple[str, ...] = (
    "price",
    "change_pct",
    "relative_volume",
    "catalyst",
    "float",
)


@dataclass(frozen=True)
class PillarCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class FivePillarsResult:
    symbol: str
    checks: tuple[PillarCheck, ...]
    pass_count: int = field(init=False)
    all_pass: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pass_count", sum(1 for c in self.checks if c.passed))
        object.__setattr__(self, "all_pass", self.pass_count == len(self.checks))

    @property
    def checkmark(self) -> str:
        """✅ only when every pillar passes; otherwise shows progress (e.g. '3/5')."""
        return "\u2705" if self.all_pass else f"{self.pass_count}/{len(self.checks)}"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "all_pass": self.all_pass,
            "pass_count": self.pass_count,
            "total": len(self.checks),
            "checkmark": self.checkmark,
            "pillars": [
                {"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks
            ],
        }


def _check_price(price: float | None) -> PillarCheck:
    if price is None:
        return PillarCheck("price", False, "no price data")
    passed = FIVE_PILLARS_MIN_PRICE <= price <= FIVE_PILLARS_MAX_PRICE
    return PillarCheck(
        "price", passed,
        f"${price:.2f} (need ${FIVE_PILLARS_MIN_PRICE:.0f}-${FIVE_PILLARS_MAX_PRICE:.0f})",
    )


def _check_change_pct(change_pct: float | None) -> PillarCheck:
    if change_pct is None:
        return PillarCheck("change_pct", False, "no change % data")
    pct = change_pct * 100 if abs(change_pct) <= 1.0 else change_pct
    passed = pct >= FIVE_PILLARS_MIN_CHANGE_PCT
    return PillarCheck(
        "change_pct", passed,
        f"{pct:.1f}% (need >= {FIVE_PILLARS_MIN_CHANGE_PCT:.0f}%)",
    )


def _check_relative_volume(rel_volume: float | None) -> PillarCheck:
    if rel_volume is None:
        return PillarCheck("relative_volume", False, "no relative volume data")
    passed = rel_volume >= FIVE_PILLARS_MIN_REL_VOLUME
    return PillarCheck(
        "relative_volume", passed,
        f"{rel_volume:.1f}x (need >= {FIVE_PILLARS_MIN_REL_VOLUME:.0f}x)",
    )


def _check_catalyst(has_news: bool | None, technical_breakout: bool = False) -> PillarCheck:
    passed = bool(has_news) or bool(technical_breakout)
    if has_news:
        detail = "news catalyst present"
    elif technical_breakout:
        detail = "technical breakout (no news)"
    else:
        detail = "no news or technical breakout"
    return PillarCheck("catalyst", passed, detail)


def _check_float(float_shares: float | None) -> PillarCheck:
    if float_shares is None:
        # Unknown float is treated as a fail — we don't guess in favor of a trade.
        return PillarCheck("float", False, "float unknown")
    passed = float_shares <= FIVE_PILLARS_MAX_FLOAT_SHARES
    return PillarCheck(
        "float", passed,
        f"{float_shares:,.0f} shares (need <= {FIVE_PILLARS_MAX_FLOAT_SHARES:,.0f})",
    )


def evaluate_five_pillars(candidate: dict, technical_breakout: bool = False) -> FivePillarsResult:
    """Evaluate the Five Pillars against one candidate dict.

    Accepts the same field names Nova's scanner already produces:
    symbol, price (or current_price), change_pct (or gap_percent), rel_volume,
    has_news, float (or float_shares).
    """
    symbol = candidate.get("symbol", "?")
    price = candidate.get("price", candidate.get("current_price"))
    change_pct = candidate.get("change_pct", candidate.get("gap_percent"))
    rel_volume = candidate.get("rel_volume")
    has_news = candidate.get("has_news")
    float_shares = candidate.get("float", candidate.get("float_shares"))

    checks = (
        _check_price(price),
        _check_change_pct(change_pct),
        _check_relative_volume(rel_volume),
        _check_catalyst(has_news, technical_breakout),
        _check_float(float_shares),
    )
    return FivePillarsResult(symbol=symbol, checks=checks)


def evaluate_many(candidates: list[dict]) -> list[FivePillarsResult]:
    """Evaluate a whole scanner list at once (e.g. the current gapper cache)."""
    return [evaluate_five_pillars(c) for c in candidates]
