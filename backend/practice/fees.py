"""IBKR-like fees for a practice fill (architecture/practice-account.md, section 2).

Commission is IBKR Pro *Fixed*: a per-share rate, never below the per-order
minimum, never above the percent-of-value cap. When the cap is below the
minimum (a tiny order) the cap wins, as on IBKR's own schedule. The SEC
section 31 fee and the FINRA Trading Activity Fee are passed through on
**sells only**. Pure functions; every number comes from ``constants_practice``
with its source named there. Nothing here is invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constants_practice import (
    PRACTICE_COMMISSION_MAX_PCT,
    PRACTICE_COMMISSION_MIN,
    PRACTICE_COMMISSION_PER_SHARE,
    PRACTICE_FINRA_TAF_MAX,
    PRACTICE_FINRA_TAF_PER_SHARE,
    PRACTICE_SEC_FEE_RATE,
)

_PLACES = 6


@dataclass(frozen=True)
class Fees:
    """What one fill cost, itemised the way an IBKR Fixed statement itemises it."""

    commission: float
    sec_fee: float = 0.0
    finra_taf: float = 0.0

    @property
    def total(self) -> float:
        return round(self.commission + self.sec_fee + self.finra_taf, _PLACES)

    def as_dict(self) -> dict[str, float]:
        return {
            "commission": self.commission,
            "sec_fee": self.sec_fee,
            "finra_taf": self.finra_taf,
            "total": self.total,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Fees":
        row = data if isinstance(data, dict) else {}
        return cls(
            commission=float(row.get("commission") or 0.0),
            sec_fee=float(row.get("sec_fee") or 0.0),
            finra_taf=float(row.get("finra_taf") or 0.0),
        )


def commission(qty: float, price: float) -> float:
    """IBKR Fixed: ``clamp(qty * rate, minimum, pct_cap * value)``; the cap wins over the minimum."""
    shares = abs(float(qty))
    px = abs(float(price))
    if shares <= 0 or px <= 0:
        return 0.0
    per_share = shares * PRACTICE_COMMISSION_PER_SHARE
    cap = PRACTICE_COMMISSION_MAX_PCT * shares * px
    return round(min(max(per_share, PRACTICE_COMMISSION_MIN), cap), _PLACES)


def regulatory(side: str, qty: float, price: float) -> tuple[float, float]:
    """``(sec_fee, finra_taf)`` on a sell; both zero on a buy."""
    if (side or "").upper() != "SELL":
        return 0.0, 0.0
    shares = abs(float(qty))
    value = shares * abs(float(price))
    sec_fee = round(value * PRACTICE_SEC_FEE_RATE, _PLACES)
    taf = round(min(shares * PRACTICE_FINRA_TAF_PER_SHARE, PRACTICE_FINRA_TAF_MAX), _PLACES)
    return sec_fee, taf


def for_fill(side: str, qty: float, price: float) -> Fees:
    """Everything one fill is charged."""
    sec_fee, taf = regulatory(side, qty, price)
    return Fees(commission=commission(qty, price), sec_fee=sec_fee, finra_taf=taf)
