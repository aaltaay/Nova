"""The size of a Nova automatic buy (ADR 042 E). Pure: one rule for the bot and Auto-entry.

Whole shares of the risk per trade over the risk per share, then cut to the sleeve's
max shares and to what its buying-power budget still buys at the entry. A size under
one share is a stated skip, never a guess.
"""
from __future__ import annotations

import math
from typing import Any

_EPS = 1e-9


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def size(risk_usd: Any, entry: Any, stop: Any, max_shares: Any, budget_left: Any) -> dict[str, Any]:
    """``{qty, by_risk, capped_by: "max_shares" | "budget" | None, text}``.

    ``by_risk`` is floor(risk / (entry - stop)); ``qty`` is that cut to ``max_shares`` and to
    floor(budget_left / entry). ``capped_by`` names the bound that cut it (the smaller, when
    both do). ``budget_left`` None means no budget applies (the operator's own size)."""
    risk, e, s = _num(risk_usd), _num(entry), _num(stop)
    if risk is None or risk <= 0:
        return {"qty": 0, "by_risk": None, "capped_by": None, "text": "no risk per trade is set"}
    if e is None or s is None or e <= 0:
        return {"qty": 0, "by_risk": None, "capped_by": None, "text": "the plan has no entry and stop to size by"}
    per_share = e - s
    if per_share <= _EPS:
        return {"qty": 0, "by_risk": None, "capped_by": None,
                "text": f"the stop {s:.2f} is not under the entry {e:.2f}: nothing to size by"}
    by_risk = int(math.floor(risk / per_share + _EPS))
    qty, capped_by = by_risk, None
    cap = _num(max_shares)
    if cap is not None and cap >= 0 and int(cap) < qty:
        qty, capped_by = int(cap), "max_shares"
    left = _num(budget_left)
    if left is not None:
        afford = max(0, int(math.floor((max(left, 0.0) + _EPS) / e)))
        if afford < qty:
            qty, capped_by = afford, "budget"
    base = f"${risk:g} risk / ${per_share:.2f} a share = {by_risk:,}"
    if qty < 1:
        if by_risk < 1:
            text = f"{base}: under one share -- Nova does not buy"
        elif capped_by == "budget":
            text = f"{base}, but the ${max(left or 0.0, 0.0):.2f} left in the budget buys no share at {e:.2f}"
        else:
            text = f"{base}, but the sleeve allows no share"
        return {"qty": 0, "by_risk": by_risk, "capped_by": capped_by, "text": text}
    shares = f"{qty:,} share{'' if qty == 1 else 's'}"
    if capped_by == "max_shares":
        text = f"{shares}: {base}, capped at the sleeve's {qty:,} max share{'' if qty == 1 else 's'}"
    elif capped_by == "budget":
        text = f"{shares}: {base}, cut to what the ${max(left or 0.0, 0.0):.2f} budget buys at {e:.2f}"
    else:
        text = f"{shares}: {base}"
    return {"qty": qty, "by_risk": by_risk, "capped_by": capped_by, "text": text}
