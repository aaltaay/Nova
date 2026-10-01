"""NOT A TRADE is one rule (ADR 042 H; operator report 2026-09-29). Pure.

A setup is **not a trade** -- each reason a sentence -- when:

- its grade is C (three pillars or fewer);
- the template's stock filter keeps the name out (filtered);
- it triggered with the tape at anything but go;
- it already played out (the scoring's first touch printed);
- the spread is at or over the risk: a buy at the ask sits at or under its stop on the bid;
- the stock is too thin to trade (``setup_scanner.liquidity``, operator decision 2026-10-01): too little
  traded today or in the last five minutes, or buying the desk's size walks the asks too far.

The Trader's plan (``stock_read.plan``), Nova's bot and Auto-entry
(``bot.first_pullback.admit``), Approve (``stock_mode.actions``) and the proposals
(``setup_scanner.lane_announce``) all ask this one function. It only reads what it is given.
"""
from __future__ import annotations

from typing import Any

from constants_setups import SETUPS_GRADE_C, TAPE_VERDICT_GO
from setup_scanner.liquidity import headline as thin_headline

EPS = 1e-9


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def spread_text(spread: float, risk: float) -> str:
    return f"the spread {spread:.2f} is at least the {risk:.2f} risk"


def spread_kills(spread: Any, risk: Any) -> bool:
    s, r = _num(spread), _num(risk)
    return s is not None and r is not None and r > EPS and s >= r - EPS


def verdict(*, grade: str | None, pillars: dict[str, Any] | None = None, filtered: str | bool | None = None,
            triggered: bool = False, tape: dict[str, Any] | None = None, played_out: str | None = None,
            spread: Any = None, risk: Any = None, liquidity: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{ok, reasons}``.

    ``pillars`` is ``{passed, known, total}``; ``filtered`` the stock filter's reason (True when
    it names none); ``tape`` ``{verdict, reasons}`` at the trigger (read only when
    ``triggered``); ``played_out`` the result's words when the first touch printed; ``liquidity`` a
    ``setup_scanner.liquidity`` reading (only a thin one is a reason)."""
    reasons: list[str] = []
    if grade == SETUPS_GRADE_C:
        reasons.append(f"grade C: {pillars['passed']} of {pillars['total']} pillars"
                       if isinstance(pillars, dict) and pillars.get("total") is not None
                       else "grade C: three pillars or fewer")
    if filtered:
        why = str(filtered).removeprefix("filtered: ") if isinstance(filtered, str) else ""
        reasons.append("the template's stock filter keeps it out" + (f": {why}" if why else ""))
    tape = tape or {}
    if triggered and tape.get("verdict") and tape["verdict"] != TAPE_VERDICT_GO:
        first = (tape.get("reasons") or [""])[0]
        reasons.append(f"it triggered with the tape at {str(tape['verdict']).upper()}" + (f": {first}" if first else ""))
    if played_out:
        reasons.append(f"it already played out: {played_out}")
    if spread_kills(spread, risk):
        reasons.append(f"{spread_text(float(spread), float(risk))}: a buy at the ask sits at or under its stop "
                       "on the bid")
    thin = thin_headline(liquidity)
    if thin:
        reasons.append(thin)
    return {"ok": not reasons, "reasons": reasons}


def of_event(event: dict[str, Any]) -> dict[str, Any]:
    """The verdict on a trigger event (the lane's ``on_trigger`` payload, ADR 042 H)."""
    setup = event.get("setup") or {}
    return verdict(grade=event.get("grade"), pillars=event.get("pillars"), filtered=event.get("filtered"),
                   triggered=True, tape=event.get("tape"), spread=event.get("spread"), risk=setup.get("risk"),
                   liquidity=event.get("liquidity"))
