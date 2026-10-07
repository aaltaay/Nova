"""LULD rules (pure): the percentage parameter, the price bands and the hours (ADR 047).

From the Limit Up-Limit Down Plan (Amendment 20, Section V and Appendix A) and the
Nasdaq LULD FAQ (2026):

- Tier 1 is the S&P 500, the Russell 1000 and listed ETPs; Tier 2 is every other NMS
  stock. Rights and warrants are not covered.
- The percentage parameter is fixed for the day by the previous close on the listing
  exchange. Over $3.00 it is 5% (Tier 1) or 10% (Tier 2). From $0.75 up to and including
  $3.00 it is 20%. Under $0.75 it is the lesser of $0.15 or 75% of the reference.
- 15:35-16:00 ET doubles it for every Tier 1 stock and for Tier 2 stocks at or under
  $3.00. Amendment 18 (February 2020) ended the doubling at the open, and at the close for
  Tier 2 over $3.00.
- Band = reference +/- reference x percentage, rounded to the nearest penny, half up:
  GRML (2026-09-22) reopened at 15.75 and paused 27 s later at 14.18 = 14.175 rounded up.
- The bands apply 09:30-16:00 ET (early closes are not modelled, as elsewhere in Nova).

Prices are exact rationals (``fractions.Fraction``), so a band never lands a cent off by a
floating-point error.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo

from constants import NOVA_OS_NYSE_HOLIDAYS
from constants_scanner import SESSION_RTH_CLOSE_MIN_ET, SESSION_RTH_OPEN_MIN_ET
from luld.constants_luld import (
    LULD_CLOSE_DOUBLE_MIN_ET,
    LULD_LOW_DOLLARS,
    LULD_LOW_PCT,
    LULD_MIN_PRICE,
    LULD_PCT_MID,
    LULD_PCT_TIER1,
    LULD_PCT_TIER2,
    LULD_PRICE_HIGH,
    LULD_PRICE_LOW,
    LULD_TIER1_MIN_MARKET_CAP,
    LULD_TIER2_MAX_MARKET_CAP,
    LULD_TIER_GUESS_MARKET_CAP,
)

ET = ZoneInfo("America/New_York")
_CENT = Fraction(1, 100)
_HALF = Fraction(1, 2)
_MIN_PRICE = Fraction(str(LULD_MIN_PRICE))


@dataclass(frozen=True)
class Parameter:
    """The day's percentage parameter: a percentage, or the low-priced dollar rule."""

    kind: str                 # "pct" | "low"
    pct: Fraction             # the percentage (the low rule's percentage leg)
    dollars: Fraction | None  # the low rule's dollar leg
    doubled: bool             # 15:35-16:00 doubling in force

    def offset(self, reference: Fraction) -> Fraction:
        if self.kind == "pct":
            return reference * self.pct
        return min(self.dollars or Fraction(0), reference * self.pct)

    def text(self) -> str:
        pct = f"{float(self.pct) * 100:g}%"
        if self.kind == "pct":
            return pct + (" (doubled 15:35-16:00)" if self.doubled else "")
        dollars = f"${float(self.dollars or 0):.2f}"
        return f"the lesser of {dollars} or {pct}" + (" (doubled 15:35-16:00)" if self.doubled else "")


def _frac(x: float) -> Fraction:
    return Fraction(str(x))


def round_cent(x: Fraction) -> Fraction:
    """To the nearest penny, half up (the exchanges' rounding, see the module note)."""
    return Fraction((x / _CENT + _HALF).__floor__()) * _CENT


def round_to(x: Fraction, digits: int) -> Fraction:
    """To ``digits`` decimals, half up."""
    unit = Fraction(1, 10 ** digits)
    return Fraction((x / unit + _HALF).__floor__()) * unit


def rth_bounds(ts: float) -> tuple[float, float] | None:
    """09:30 and 16:00 ET of ``ts``'s Eastern date as epoch seconds; None on a weekend or a holiday."""
    day = datetime.fromtimestamp(ts, ET).date()
    if day.weekday() >= 5 or day.isoformat() in NOVA_OS_NYSE_HOLIDAYS:
        return None
    midnight = datetime(day.year, day.month, day.day, tzinfo=ET)
    return ((midnight + timedelta(minutes=SESSION_RTH_OPEN_MIN_ET)).timestamp(),
            (midnight + timedelta(minutes=SESSION_RTH_CLOSE_MIN_ET)).timestamp())


def closing_at(ts: float) -> float:
    """15:35 ET of ``ts``'s Eastern date, when the closing doubling starts."""
    day = datetime.fromtimestamp(ts, ET).date()
    midnight = datetime(day.year, day.month, day.day, tzinfo=ET)
    return (midnight + timedelta(minutes=LULD_CLOSE_DOUBLE_MIN_ET)).timestamp()


def parameter(prev_close: float | None, tier: int | None, *, closing: bool) -> Parameter | None:
    """The percentage parameter for a previous close; None when it cannot be known.

    The tier decides only over $3.00 (at or under it, both tiers share every number), so
    ``tier`` may be None there."""
    if prev_close is None or prev_close <= 0:
        return None
    close = _frac(prev_close)
    if close > _frac(LULD_PRICE_HIGH):
        if tier not in (1, 2):
            return None
        double = closing and tier == 1
        pct = _frac(LULD_PCT_TIER1 if tier == 1 else LULD_PCT_TIER2)
        return Parameter("pct", pct * (2 if double else 1), None, double)
    if close >= _frac(LULD_PRICE_LOW):
        return Parameter("pct", _frac(LULD_PCT_MID) * (2 if closing else 1), None, closing)
    mult = 2 if closing else 1
    return Parameter("low", _frac(LULD_LOW_PCT) * mult, _frac(LULD_LOW_DOLLARS) * mult, closing)


def bands(reference: Fraction, param: Parameter) -> tuple[Fraction | None, Fraction]:
    """(lower, upper), each rounded to the penny; no lower band under one cent."""
    off = param.offset(reference)
    lower = round_cent(reference - off)
    return (lower if lower >= _MIN_PRICE else None), round_cent(reference + off)


def tier_needed(prev_close: float | None) -> bool:
    """True when the band depends on the tier: a previous close over $3.00."""
    return prev_close is not None and prev_close > LULD_PRICE_HIGH


def tier_from_size(market_cap: float | None) -> tuple[int, str, bool]:
    """The tier Nova reads from the company's size: (tier, how it read it, sure).

    Nova keeps no index membership list (ADR 047). A company of at least
    ``LULD_TIER1_MIN_MARKET_CAP`` is in the Russell 1000 and one of at most
    ``LULD_TIER2_MAX_MARKET_CAP`` is not: sure. Between them Nova takes the likelier side of
    ``LULD_TIER_GUESS_MARKET_CAP`` (about the Russell 1000's cut-off), and with no size known
    Tier 2, which nearly every stock that halts is -- neither sure, and the desk says so."""
    if market_cap is None or market_cap <= 0:
        return 2, "its market cap is not known: Tier 2 assumed (nearly every stock that halts is)", False
    size = _cap_words(market_cap)
    if market_cap >= LULD_TIER1_MIN_MARKET_CAP:
        return 1, f"a {size} company: in the S&P 500 / Russell 1000 (Tier 1)", True
    if market_cap <= LULD_TIER2_MAX_MARKET_CAP:
        return 2, f"a {size} company: too small for the Russell 1000 (Tier 2)", True
    if market_cap >= LULD_TIER_GUESS_MARKET_CAP:
        return 1, f"a {size} company: probably in the Russell 1000 (Tier 1 assumed)", False
    return 2, f"a {size} company: probably not in the Russell 1000 (Tier 2 assumed)", False


def _cap_words(cap: float) -> str:
    if cap >= 1e9:
        return f"${cap / 1e9:.1f}B"
    return f"${cap / 1e6:.0f}M"


_WARRANT_RIGHT = re.compile(r"^[A-Z]{4}[WR]$|[ ./](WS|WT|RT|W|R)$")


def covered(symbol: str, stock_type: str | None = None) -> tuple[bool, str | None]:
    """Is the stock under LULD? Rights and warrants are not (Appendix A, II(1)).

    IBKR's stock type decides when known; otherwise the symbol's form does: a Nasdaq
    fifth letter W or R, or a ``WS`` / ``RT`` class."""
    kind = (stock_type or "").strip().upper()
    if kind in {"WAR", "WARRANT", "RIGHT", "RIGHTS"}:
        return False, "LULD does not cover warrants and rights"
    if kind:
        return True, None
    if _WARRANT_RIGHT.search((symbol or "").strip().upper()):
        return False, "LULD does not cover warrants and rights (the symbol reads as one)"
    return True, None
