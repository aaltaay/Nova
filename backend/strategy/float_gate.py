"""What a max-float gate may conclude from a float Yahoo's own counts contradict (#532).

Yahoo's float is its last filing's cover count less insiders, blind to any dilution since;
``fundamentals.float_credibility`` flags a float its own shares outstanding or short interest
contradicts (``float_contradicted``). The fact that still holds is float <= shares outstanding.
So a contradicted float passes a max-float gate only when shares outstanding is itself at or
under the limit; otherwise the float is unknown and never a pass -- not even at a gate that lets
an unknown float through. A float that is not contradicted (``float_contradicted`` false, or null:
unchecked) is judged exactly as before.

Every max-float gate reads this one rule: HOD Momo's ``max_float``, the setup grade's float
pillar and a template's stock filter, the Five Pillars float pillar and the Contenders float
score, and the leaderboard's ``LEADERS_RULES``. Pure: no I/O, no clock.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if isfinite(out) and out > 0 else None


def _shares(n: float) -> str:
    """54K, 8.45M, 1.20B -- the counts a reason names."""
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}K"
    return f"{n:.0f}"


def is_contradicted(flag: Any) -> bool:
    """``float_contradicted`` as stated: true, or 1 as SQLite hands it back. False and null are not."""
    return flag is True or (type(flag) is int and flag == 1)


def float_for_gate(
    float_shares: Any, limit: float, *, contradicted: Any = None, shares_outstanding: Any = None,
) -> tuple[bool | None, str | None]:
    """A max-float gate's verdict on ``float_shares <= limit``: ``(passes, reason)``.

    A float that is not contradicted gives ``reason`` None and ``passes`` the plain comparison (None
    when there is no float); the gate keeps its own words and its own handling of an unknown float,
    so nothing changes for it.

    A contradicted float always gives a reason. ``passes`` is True when shares outstanding is at or
    under ``limit`` (the float cannot be larger); else None: the float is unknown, and never a pass.
    """
    f = _positive(float_shares)
    if f is None or not is_contradicted(contradicted):
        if isinstance(float_shares, bool) or not isinstance(float_shares, (int, float)):
            return None, None
        return (float(float_shares) <= limit if isfinite(float(float_shares)) else None), None
    out = _positive(shares_outstanding)
    head = f"float {_shares(f)} is contradicted by its own share counts"
    if out is not None and out <= limit:
        return True, f"{head}; passes on {_shares(out)} shares outstanding, at or under {_shares(limit)}"
    if out is None:
        return None, f"{head} and shares outstanding is unknown -- float unknown, not a pass"
    return None, f"{head} and {_shares(out)} shares outstanding is over {_shares(limit)} -- float unknown, not a pass"
