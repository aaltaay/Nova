"""The size of a Nova automatic entry (ADR 042 E), long or short (ADR 049, #778 step 5). Pure: one rule
for the bot and Auto-entry.

Whole shares of the risk per trade over the risk per share -- the entry less the stop on a long, the buy
stop less the entry on a short -- then cut to the sleeve's max shares and to what its buying-power budget
still holds at the entry (a short's value counts like a long's). A size under one share is a stated skip,
never a guess.
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


def size(risk_usd: Any, entry: Any, stop: Any, max_shares: Any, budget_left: Any,
         side: str = "long") -> dict[str, Any]:
    """``{qty, by_risk, capped_by: "max_shares" | "budget" | None, text}``.

    ``by_risk`` is floor(risk / (entry - stop)) on a long, floor(risk / (stop - entry)) on a short;
    ``qty`` is that cut to ``max_shares`` and to floor(budget_left / entry). ``capped_by`` names the
    bound that cut it (the smaller, when both do). ``budget_left`` None means no budget applies (the
    operator's own size)."""
    risk, e, s = _num(risk_usd), _num(entry), _num(stop)
    short = side == "short"
    verb = "short" if short else "buy"
    if risk is None or risk <= 0:
        return {"qty": 0, "by_risk": None, "capped_by": None, "text": "no risk per trade is set"}
    if e is None or s is None or e <= 0:
        return {"qty": 0, "by_risk": None, "capped_by": None, "text": "the plan has no entry and stop to size by"}
    per_share = s - e if short else e - s
    if per_share <= _EPS:
        where = f"the buy stop {s:.2f} is not over" if short else f"the stop {s:.2f} is not under"
        return {"qty": 0, "by_risk": None, "capped_by": None,
                "text": f"{where} the entry {e:.2f}: nothing to size by"}
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
            text = f"{base}: under one share -- Nova does not {verb}"
        elif capped_by == "budget":
            text = (f"{base}, but the ${max(left or 0.0, 0.0):.2f} left in the budget {verb}s no share at "
                    f"{e:.2f}")
        else:
            text = f"{base}, but the sleeve allows no share"
        return {"qty": 0, "by_risk": by_risk, "capped_by": capped_by, "text": text}
    shares = f"{qty:,} share{'' if qty == 1 else 's'}"
    if capped_by == "max_shares":
        text = f"{shares}: {base}, capped at the sleeve's {qty:,} max share{'' if qty == 1 else 's'}"
    elif capped_by == "budget":
        text = f"{shares}: {base}, cut to what the ${max(left or 0.0, 0.0):.2f} budget {verb}s at {e:.2f}"
    else:
        text = f"{shares}: {base}"
    return {"qty": qty, "by_risk": by_risk, "capped_by": capped_by, "text": text}
