"""How the read decided (ADR 028 amendment, the Catalyst column 2026-10-12): every cause in the rules' order,
whether it fits, and why -- the ladder the Catalyst hover shows under the likely cause.

``steps(...)`` answers ``[{kind, name, fits, why}]``: first the move itself (``move``: a change of 10% either way,
else the cause is ``not_moving``), then each cause ``rules._likely`` tries, in its order:
``fits`` is ``true`` / ``false``, or ``null`` when a fact it needs is unknown, and ``why`` says it with the
numbers the checks hold ("Shorts 10% of float · 0.3 days to cover -- heavy is 20% of the float, or 3+ days to
cover with 10% short"). It reads the same checks and the same thresholds as ``rules._likely``, so the first step
that fits is the likely cause (a test holds the two together); it explains, it never decides. Pure.

Owner: this module (no state).
"""
from __future__ import annotations

from typing import Any

from constants_move_reason import (
    MOVE_BORROW_FEE_HIGH,
    MOVE_BORROW_SCARCE_SHARES,
    MOVE_DAYS_TO_COVER_HIGH,
    MOVE_KIND_LOW_FLOAT_MOMENTUM,
    MOVE_KIND_NEWS,
    MOVE_KIND_NEWS_PENDING,
    MOVE_KIND_ROUTINE_NEWS,
    MOVE_KIND_SHORT_SQUEEZE,
    MOVE_KIND_SPLIT_SQUEEZE,
    MOVE_KIND_THIN_TRADING,
    MOVE_KIND_UNEXPLAINED,
    MOVE_LOW_FLOAT_SHARES,
    MOVE_MIN_CHANGE,
    MOVE_ROTATION_HIGH,
    MOVE_ROTATION_SQUEEZE,
    MOVE_ROTATION_THIN,
    MOVE_RVOL_SQUEEZE,
    MOVE_RVOL_THIN,
    MOVE_SHORT_PCT_HIGH,
    MOVE_SHORT_PCT_WITH_DTC,
    MOVE_SPLIT_RECENT_DAYS,
    MOVE_STEP_MOVE,
    MOVE_STATE_UNKNOWN,
    MOVE_STATE_YES,
)

_NAMES = {
    MOVE_STEP_MOVE: "A real move",
    MOVE_KIND_NEWS_PENDING: "Halted for news",
    MOVE_KIND_NEWS: "Company news",
    MOVE_KIND_SHORT_SQUEEZE: "Short squeeze",
    MOVE_KIND_ROUTINE_NEWS: "Routine item",
    MOVE_KIND_SPLIT_SQUEEZE: "Split squeeze",
    MOVE_KIND_LOW_FLOAT_MOMENTUM: "Low-float momentum",
    MOVE_KIND_THIN_TRADING: "Thin trading",
    MOVE_KIND_UNEXPLAINED: "Unexplained",
}
_SHORT_RULE = (f"heavy is {MOVE_SHORT_PCT_HIGH * 100:.0f}% of the float short, or {MOVE_DAYS_TO_COVER_HIGH:g}+ days "
               f"to cover with {MOVE_SHORT_PCT_WITH_DTC * 100:.0f}%+ short")
_BORROW_RULE = (f"tight is a {MOVE_BORROW_FEE_HIGH:.0f}%+ fee, a fee doubled since the open, three quarters of the "
                f"lendable shares gone, or under {MOVE_BORROW_SCARCE_SHARES / 1000:.0f}K to lend")
_LOW_FLOAT = f"under {MOVE_LOW_FLOAT_SHARES / 1e6:.0f}M"


def _times(x: float) -> str:
    return f"{x:,.0f}x" if x >= 10 else f"{x:.1f}x"


def _pct(change: float) -> str:
    return f"{change * 100:+.1f}%"


def _step(kind: str, fits: bool | None, why: str) -> dict[str, Any]:
    return {"kind": kind, "name": _NAMES[kind], "fits": fits, "why": why}


def _all(parts: list[tuple[bool | None, str]]) -> tuple[bool | None, str]:
    """Every part must hold: any ``False`` fails (its reasons said), else any ``None`` is unknown."""
    failed = [why for ok, why in parts if ok is False]
    if failed:
        return False, "; ".join(failed)
    unknown = [why for ok, why in parts if ok is None]
    if unknown:
        return None, "; ".join(unknown)
    return True, "; ".join(why for _, why in parts)


def _short(text: str, limit: int = 80) -> str:
    """A headline cut to a rung's width at a word ("... "); the whole headline is the read's ``facts.catalyst``."""
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def _value(c: dict[str, Any]) -> str:
    return str(c.get("value") or "unknown")


def steps(change: float | None, by: dict[str, dict[str, Any]], rot: float | None, rvol: float | None,
          verdict: Any, headline: str | None) -> list[dict[str, Any]]:
    """The ladder for one read; ``by`` is the checks by id, as ``rules.read`` built them."""
    if change is None:
        return [_step(MOVE_STEP_MOVE, None, "No price change on record")]
    if abs(change) < MOVE_MIN_CHANGE:
        return [_step(MOVE_STEP_MOVE, False,
                      f"{_pct(change)} today -- under the {MOVE_MIN_CHANGE * 100:.0f}% move line either way")]
    out = [_step(MOVE_STEP_MOVE, True, f"{_pct(change)} today")]
    v = verdict if isinstance(verdict, dict) else {}
    news, up = by["news"], change > 0
    news_unknown = news["state"] == MOVE_STATE_UNKNOWN

    pending = bool(v.get("news_pending"))
    out.append(_step(MOVE_KIND_NEWS_PENDING, pending, _value(news) if pending else "Not halted for news"))

    if v.get("verdict") in ("catalyst", "negative"):
        out.append(_step(MOVE_KIND_NEWS, True, _value(news) + (f": {_short(headline)}" if headline else "")))
    elif news_unknown:
        out.append(_step(MOVE_KIND_NEWS, None, "News not read yet"))
    else:
        out.append(_step(MOVE_KIND_NEWS, False, _value(news)))

    is_up = (True, f"Up {_pct(change)}") if up else (False, f"Not up ({_pct(change)})")
    out.append(_step(MOVE_KIND_SHORT_SQUEEZE, *_all([is_up, _shorts(by["short_interest"]), _borrow(by["borrow"]),
                                                     _squeeze_volume(rot, rvol)])))

    routine = v.get("verdict") == "routine_only"
    out.append(_step(MOVE_KIND_ROUTINE_NEWS, routine,
                     _value(news) + (f": {_short(headline)}" if routine and headline else "") if routine
                     else "Not a routine-only item"))

    low_float, turned = _low_float(by["float"]), _turned(rot)
    out.append(_step(MOVE_KIND_SPLIT_SQUEEZE, *_all([is_up, low_float, turned, _recent_split(by["reverse_split"])])))
    out.append(_step(MOVE_KIND_LOW_FLOAT_MOMENTUM, *_all([is_up, low_float, turned])))
    out.append(_step(MOVE_KIND_THIN_TRADING, *_thin(rot, rvol)))
    found = any(s["fits"] is True for s in out[1:])
    out.append(_step(MOVE_KIND_UNEXPLAINED, not found,
                     "A cause above fits" if found else "None of the causes above fits the facts on file"))
    return out


def _shorts(c: dict[str, Any]) -> tuple[bool | None, str]:
    if c["state"] == MOVE_STATE_UNKNOWN:
        return None, "Short interest unknown"
    return c["state"] == MOVE_STATE_YES, f"Shorts {_value(c)}" + ("" if c["state"] == MOVE_STATE_YES
                                                                  else f" -- {_SHORT_RULE}")


def _borrow(c: dict[str, Any]) -> tuple[bool | None, str]:
    if c["state"] == MOVE_STATE_UNKNOWN:
        return None, f"Borrow {_value(c).lower()}"
    return c["state"] == MOVE_STATE_YES, f"Borrow: {_value(c)}" + ("" if c["state"] == MOVE_STATE_YES
                                                                   else f" -- {_BORROW_RULE}")


def _squeeze_volume(rot: float | None, rvol: float | None) -> tuple[bool | None, str]:
    said = ", ".join(p for p in ((f"float traded {_times(rot)}" if rot is not None else None),
                                 (f"RVOL {_times(rvol)}" if rvol is not None else None)) if p)
    if (rot is not None and rot >= MOVE_ROTATION_SQUEEZE) or (rvol is not None and rvol >= MOVE_RVOL_SQUEEZE):
        return True, f"Volume: {said}"
    if rot is None and rvol is None:
        return None, "Volume unknown"
    return False, (f"Volume: {said} -- needs the float traded {MOVE_ROTATION_SQUEEZE:g}x or RVOL "
                   f"{MOVE_RVOL_SQUEEZE:g}x")


def _low_float(c: dict[str, Any]) -> tuple[bool | None, str]:
    if c["state"] == MOVE_STATE_UNKNOWN:
        return None, f"Float {_value(c)} -- unknown" + (f" ({c['detail']})" if c.get("detail") else "")
    if c["state"] == MOVE_STATE_YES:
        return True, f"Float {_value(c)}"
    return False, f"Float {_value(c)} -- low is {_LOW_FLOAT}"


def _turned(rot: float | None) -> tuple[bool | None, str]:
    if rot is None:
        return None, "Volume over the float unknown"
    if rot >= MOVE_ROTATION_HIGH:
        return True, f"Float traded {_times(rot)}"
    return False, f"Float traded {_times(rot)} -- needs {MOVE_ROTATION_HIGH:g}x"


def _recent_split(c: dict[str, Any]) -> tuple[bool | None, str]:
    if c["state"] == MOVE_STATE_UNKNOWN:
        return None, "Split history unknown"
    if c["state"] == MOVE_STATE_YES:
        return True, f"Reverse split {_value(c)}"
    return False, f"Reverse split: {_value(c)} -- needs one in the last {MOVE_SPLIT_RECENT_DAYS} days"


def _thin(rot: float | None, rvol: float | None) -> tuple[bool | None, str]:
    if rvol is not None:
        if rvol < MOVE_RVOL_THIN:
            return True, f"RVOL {_times(rvol)} -- below its usual volume"
        return False, f"RVOL {_times(rvol)} -- not below its usual volume"
    if rot is not None:
        if rot < MOVE_ROTATION_THIN:
            return True, f"Float traded {_times(rot)} -- under a tenth of the float (RVOL unknown)"
        return False, f"Float traded {_times(rot)} (RVOL unknown)"
    return None, "Volume unknown"

