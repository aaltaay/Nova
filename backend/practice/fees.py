"""IBKR-like fees for a practice fill (architecture/practice-account.md, section 2).

Commission is IBKR Pro *Fixed*: a per-share rate, never below the per-order
minimum, never above the percent-of-value cap. When the cap is below the
minimum (a tiny order) the cap wins, as on IBKR's own schedule. The SEC
section 31 fee and the FINRA Trading Activity Fee are passed through on
**sells only** -- the TAF not at all on a trade date inside a FINRA TAF
holiday -- and the FINRA CAT fee on **every** fill. Pure functions; every
number comes from ``constants_practice`` with its source named there. Nothing
here is invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constants_practice import (
    PRACTICE_COMMISSION_MAX_PCT,
    PRACTICE_COMMISSION_MIN,
    PRACTICE_COMMISSION_PER_SHARE,
    PRACTICE_FINRA_CAT_PER_SHARE,
    PRACTICE_FINRA_TAF_HOLIDAYS,
    PRACTICE_FINRA_TAF_MAX,
    PRACTICE_FINRA_TAF_PER_SHARE,
    PRACTICE_SEC_FEE_RATE,
)
from practice import clock

_PLACES = 6


@dataclass(frozen=True)
class Fees:
    """What one fill cost, itemised the way an IBKR Fixed statement itemises it."""

    commission: float
    sec_fee: float = 0.0
    finra_taf: float = 0.0
    finra_cat: float = 0.0

    @property
    def regulatory(self) -> float:
        """The SEC and FINRA pass-throughs: everything but the commission."""
        return round(self.sec_fee + self.finra_taf + self.finra_cat, _PLACES)

    @property
    def total(self) -> float:
        return round(self.commission + self.regulatory, _PLACES)

    def as_dict(self) -> dict[str, float]:
        return {
            "commission": self.commission,
            "sec_fee": self.sec_fee,
            "finra_taf": self.finra_taf,
            "finra_cat": self.finra_cat,
            "total": self.total,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Fees":
        """A stored fill's fees; a fill made before a fee existed reads it as 0 (what it was charged)."""
        row = data if isinstance(data, dict) else {}
        return cls(
            commission=float(row.get("commission") or 0.0),
            sec_fee=float(row.get("sec_fee") or 0.0),
            finra_taf=float(row.get("finra_taf") or 0.0),
            finra_cat=float(row.get("finra_cat") or 0.0),
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


def taf_holiday(ts: float | None) -> bool:
    """True when ``ts``'s Eastern trade date falls in a FINRA TAF holiday.

    An unknown time is never a holiday: the standing rate is charged, so a
    practice fill is never cheaper than Live by a guess.
    """
    if ts is None:
        return False
    day = clock.at(ts).date().isoformat()
    return any(start <= day <= end for start, end in PRACTICE_FINRA_TAF_HOLIDAYS)


def regulatory(side: str, qty: float, price: float, ts: float | None = None) -> tuple[float, float]:
    """``(sec_fee, finra_taf)`` on a sell traded at ``ts``; both zero on a buy."""
    if (side or "").upper() != "SELL":
        return 0.0, 0.0
    shares = abs(float(qty))
    value = shares * abs(float(price))
    sec_fee = round(value * PRACTICE_SEC_FEE_RATE, _PLACES)
    taf = 0.0 if taf_holiday(ts) else round(
        min(shares * PRACTICE_FINRA_TAF_PER_SHARE, PRACTICE_FINRA_TAF_MAX), _PLACES)
    return sec_fee, taf


def cat(qty: float) -> float:
    """FINRA CAT on every share executed, bought or sold."""
    return round(abs(float(qty)) * PRACTICE_FINRA_CAT_PER_SHARE, _PLACES)


def for_fill(side: str, qty: float, price: float, ts: float | None = None) -> Fees:
    """Everything one fill traded at ``ts`` (the venue's time) is charged."""
    sec_fee, taf = regulatory(side, qty, price, ts)
    charge = commission(qty, price)
    return Fees(commission=charge, sec_fee=sec_fee, finra_taf=taf,
                finra_cat=cat(qty) if charge > 0 else 0.0)
