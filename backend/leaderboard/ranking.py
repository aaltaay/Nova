"""The one leaderboard ranking (ADR 023) -- pure, no I/O, no clock.

Three callers share it so they can never disagree about who led:

* playback (``leaderboard.playback``) orders a stored minute and names its leaders;
* the S5 rolling universe (``research/leaderboard``) picks its names offline;
* live auto-record (``leaderboard.auto_record``) picks what to record 07:00-10:00.

A row qualifies first, then qualified rows are ordered by ``change_pct``
(biggest gainer first; an unknown change sorts last), ties broken by volume
then symbol so the order is total and repeatable. A value a rule needs but the
row does not carry fails the rule -- except float, which ``float_unknown_ok``
may admit -- so an unknown is never read as a pass.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_LEADERS_MAX_FLOAT,
    LEADERBOARD_LEADERS_MAX_PRICE,
    LEADERBOARD_LEADERS_MIN_PRICE,
    LEADERBOARD_LEADERS_MIN_VOLUME,
    LEADERBOARD_LEADERS_TOP_N,
    LEADERBOARD_RVOL_BASIS_TOD,
    LEADERBOARD_S5_MIN_RVOL,
    LEADERBOARD_S5_TOP_N,
)


@dataclass(frozen=True)
class RankingRules:
    """Who qualifies. ``None`` means the rule is off."""

    min_price: float | None = None
    max_price: float | None = None
    max_float: float | None = None
    float_unknown_ok: bool = True
    min_volume: float | None = None
    min_rvol: float | None = None
    # With min_rvol set, only a row whose rvol_basis is this one can pass.
    rvol_basis: str | None = None
    min_change_pct: float | None = None
    top_n: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BOARD_RULES = RankingRules()
LEADERS_RULES = RankingRules(
    min_price=LEADERBOARD_LEADERS_MIN_PRICE,
    max_price=LEADERBOARD_LEADERS_MAX_PRICE,
    max_float=LEADERBOARD_LEADERS_MAX_FLOAT,
    float_unknown_ok=True,
    min_volume=LEADERBOARD_LEADERS_MIN_VOLUME,
    min_change_pct=0.0,
    top_n=LEADERBOARD_LEADERS_TOP_N,
)
S5_RULES = RankingRules(
    min_rvol=LEADERBOARD_S5_MIN_RVOL,
    rvol_basis=LEADERBOARD_RVOL_BASIS_TOD,
    min_change_pct=0.0,
    top_n=LEADERBOARD_S5_TOP_N,
)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if isfinite(out) else None


def refusal(row: Mapping[str, Any], rules: RankingRules) -> str | None:
    """The first rule ``row`` fails, or None when it qualifies."""
    price = _num(row.get("price"))
    change = _num(row.get("change_pct"))
    if rules.min_change_pct is not None:
        if change is None:
            return "change_unknown"
        if change <= rules.min_change_pct:
            return "change"
    if rules.min_price is not None or rules.max_price is not None:
        if price is None:
            return "price_unknown"
        if rules.min_price is not None and price < rules.min_price:
            return "price"
        if rules.max_price is not None and price > rules.max_price:
            return "price"
    if rules.max_float is not None:
        float_shares = _num(row.get("float_shares"))
        if float_shares is None:
            if not rules.float_unknown_ok:
                return "float_unknown"
        elif float_shares > rules.max_float:
            return "float"
    if rules.min_volume is not None:
        volume = _num(row.get("volume"))
        if volume is None:
            return "volume_unknown"
        if volume < rules.min_volume:
            return "volume"
    if rules.min_rvol is not None:
        rvol = _num(row.get("rvol"))
        if rvol is None:
            return "rvol_unknown"
        if rules.rvol_basis is not None and row.get("rvol_basis") != rules.rvol_basis:
            return "rvol_basis"
        if rvol < rules.min_rvol:
            return "rvol"
    return None


def _order_key(row: Mapping[str, Any]) -> tuple[float, float, str]:
    change = _num(row.get("change_pct"))
    volume = _num(row.get("volume"))
    return (
        -(change if change is not None else float("-inf")),
        -(volume if volume is not None else 0.0),
        str(row.get("symbol") or ""),
    )


def rank_rows(rows: Iterable[Mapping[str, Any]], rules: RankingRules = BOARD_RULES) -> list[dict[str, Any]]:
    """Qualified rows, best first, as copies carrying ``rank`` 1..n.

    One row per symbol: a duplicate symbol keeps its better-ordered row.
    """
    seen: set[str] = set()
    kept: list[Mapping[str, Any]] = []
    for row in sorted(rows, key=_order_key):
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        if refusal(row, rules) is not None:
            continue
        seen.add(symbol)
        kept.append(row)
    if rules.top_n is not None:
        kept = kept[: max(0, int(rules.top_n))]
    return [{**row, "rank": index} for index, row in enumerate(kept, start=1)]


def leader_symbols(rows: Iterable[Mapping[str, Any]], rules: RankingRules = LEADERS_RULES) -> list[str]:
    """Just the symbols, in rank order -- what auto-record and playback compare."""
    return [str(row["symbol"]).strip().upper() for row in rank_rows(rows, rules)]
