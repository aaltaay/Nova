"""The Live short proof as the door reads it and as the Bot card shows it (ADR 048 step 6).

``status()`` -> ``(complete, what is missing)``: three reviewed Paper days with shorts and the four drills,
from memory only (the door reads it under its lock). A proof file Nova cannot read is incomplete.

``view()`` is ``GET /api/short-proof``: the operator's steps (#778, §7) in order, each ticked from what Nova
sees -- ``{id, label, ok: true | false | null, text, value, seen: "nova" | "operator", enforced, how, at}``
(``ok`` null: not known, never a pass) -- with the days, the drills, and why no day can be marked yet.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_shorts import (
    SHORT_PROOF_DAYS_NEEDED,
    SHORT_PROOF_DRILLS,
    SHORT_PROOF_REVIEW_OPEN,
    SHORT_PROOF_REVIEW_WAIT,
    SHORT_PROOF_SCHEMA_VERSION,
)
from short_proof import store

logger = logging.getLogger(__name__)

DRILL_LABELS = {
    "freeze": "Freeze all orders with a short open",
    "flatten": "Flatten with a short open",
    "day_cover": "The 15:55 cover",
    "gateway_drop": "A Gateway drop with a short open",
}
DRILL_HOW = {
    "freeze": ("With a short open on Paper, press Freeze all orders (Bots page): its buy stop must stay resting. "
               "Reset the switch afterwards."),
    "flatten": "With a short open on Paper, press Flatten on its Trader tab (or the Cover all hotkey).",
    "day_cover": "Hold a short on Paper past 15:55 ET: Nova covers it at market.",
    "gateway_drop": ("With a short open on Paper, close IB Gateway (or drop the network) and bring it back: the "
                     "short keeps its buy stop."),
}


def _reviewed(doc: dict[str, Any]) -> list[str]:
    """Days the operator marked reviewed -- none until how a day is reviewed is answered (#778, question 3)."""
    if not SHORT_PROOF_REVIEW_OPEN:
        return []
    return sorted(day for day, review in (doc.get("reviews") or {}).items()
                  if isinstance(review, dict) and review.get("ok") is True and day in doc["days"])


def _missing(doc: dict[str, Any]) -> str:
    parts = []
    reviewed = len(_reviewed(doc))
    if reviewed < SHORT_PROOF_DAYS_NEEDED:
        days = len(doc["days"])
        parts.append(f"{reviewed} of {SHORT_PROOF_DAYS_NEEDED} reviewed Paper days with shorts ({days} with shorts "
                     "so far; no day can be marked reviewed until #778's question 3 is answered)"
                     if not SHORT_PROOF_REVIEW_OPEN else
                     f"{reviewed} of {SHORT_PROOF_DAYS_NEEDED} reviewed Paper days with shorts")
    left = [DRILL_LABELS[name] for name in SHORT_PROOF_DRILLS if doc["drills"][name]["passed"] is None]
    if left:
        parts.append("the drills still to run on Paper: " + ", ".join(left))
    return "; ".join(parts) + "."


def status() -> tuple[bool, str]:
    """``(complete, what is missing)`` for the door; memory only."""
    doc, error = store.read()
    if doc is None:
        return False, f"the proof could not be read ({error})."
    complete = (len(_reviewed(doc)) >= SHORT_PROOF_DAYS_NEEDED
                and all(doc["drills"][name]["passed"] is not None for name in SHORT_PROOF_DRILLS))
    return complete, ("" if complete else _missing(doc))


def done(doc: dict[str, Any] | None) -> tuple[int, int]:
    """``(items done, items)`` of the proof: the reviewed days (to 3) and the drills."""
    total = SHORT_PROOF_DAYS_NEEDED + len(SHORT_PROOF_DRILLS)
    if doc is None:
        return 0, total
    drills = sum(1 for name in SHORT_PROOF_DRILLS if doc["drills"][name]["passed"] is not None)
    return min(len(_reviewed(doc)), SHORT_PROOF_DAYS_NEEDED) + drills, total


def _step(sid: str, label: str, ok: bool | None, text: str, *, value: str | None = None, seen: str = "nova",
          enforced: bool = False, how: str | None = None, at: float | None = None) -> dict[str, Any]:
    return {"id": sid, "label": label, "ok": ok, "text": text, "value": value, "seen": seen, "enforced": enforced,
            "how": how, "at": at}


def _margin_step() -> dict[str, Any]:
    from ibkr import client as _client
    from ibkr import live_book

    label = "Margin account"
    how = "Fund the IBKR margin account and log IB Gateway in to Live: IBKR's figures must show it as margin."
    if _client.account_mode() == "paper":
        return _step("margin_account", label, None, ("IBKR's session is the paper Gateway, so Nova cannot see the "
                                                     "Live account."), enforced=True, how=how)
    try:
        summary = live_book.account_summary()
    except Exception as exc:
        return _step("margin_account", label, None, f"IBKR is not ready, so Nova cannot see the Live account ({exc}).",
                     enforced=True, how=how)
    if summary.get("pending"):
        return _step("margin_account", label, None, "The Live account has not loaded yet.", enforced=True, how=how)
    ibkr_cls = str(summary.get("ibkr_account_class") or "")
    if ibkr_cls == "margin":
        return _step("margin_account", label, True, "IBKR shows a margin account.", value="margin", enforced=True)
    said = ("IBKR's figures show a cash account" if ibkr_cls == "cash" else "IBKR's figures do not show the class")
    if summary.get("account_class_source") == "override":
        said += " (the IBKR_ACCOUNT_CLASS override in .env never counts for a short)"
    return _step("margin_account", label, False, said + ".", value=ibkr_cls or None, enforced=True, how=how)


def _reset_step() -> dict[str, Any]:
    from constants_practice import PRACTICE_STARTING_CASH
    from practice.broker import for_venue

    label = "Paper reset to $5,000"
    how = "Press Reset to $5,000 on the Account page (Paper); it archives the old ledger, whose history stays."
    try:
        cash = float(for_venue("paper").ledger.starting_cash)
    except Exception as exc:
        logger.warning("short proof: the Paper ledger could not be read for its starting cash", exc_info=True)
        return _step("practice_reset", label, None, f"The Paper ledger could not be read ({exc}).", how=how)
    if abs(cash - PRACTICE_STARTING_CASH) < 0.005:
        return _step("practice_reset", label, True, f"Paper starts at ${cash:,.0f}.", value=f"${cash:,.0f}")
    return _step("practice_reset", label, False, f"Paper starts at ${cash:,.0f}, not ${PRACTICE_STARTING_CASH:,.0f}.",
                 value=f"${cash:,.0f}", how=how)


def _tests_step() -> dict[str, Any]:
    from constants_bot import BOT_SHORT_SETUPS
    from constants_short_setups import SHORT_TEST_FAILED, SHORT_TEST_PASSED
    from setup_scanner import short_tests

    label = "Five-year tests run"
    states = {}
    for setup in BOT_SHORT_SETUPS:
        got = short_tests.test_in_play(setup) or {}
        states[setup] = str(got.get("state") or "")
    ran = [s for s, state in states.items() if state in (SHORT_TEST_PASSED, SHORT_TEST_FAILED)]
    words = ", ".join(f"{s.replace('_', ' ')} {state or 'unknown'}" for s, state in states.items())
    ok = len(ran) == len(BOT_SHORT_SETUPS)
    return _step("short_tests", label, ok, f"{len(ran)} of {len(BOT_SHORT_SETUPS)} have a result: {words}.",
                 value=f"{len(ran)} of {len(BOT_SHORT_SETUPS)}",
                 how=None if ok else "Run the command each short strategy's card names, on the desk (research/shorts).")


def _days_step(doc: dict[str, Any] | None, error: str | None) -> dict[str, Any]:
    label = f"{SHORT_PROOF_DAYS_NEEDED} Paper days with shorts, reviewed"
    if doc is None:
        return _step("paper_days", label, None, f"The proof could not be read ({error}).", seen="operator",
                     enforced=True)
    days, reviewed = len(doc["days"]), len(_reviewed(doc))
    text = (f"{days} Paper day{'s' if days != 1 else ''} with shorts; {reviewed} of {SHORT_PROOF_DAYS_NEEDED} "
            "reviewed (no wrong refusal or wrong fill).")
    if not SHORT_PROOF_REVIEW_OPEN:
        text += " " + SHORT_PROOF_REVIEW_WAIT
    return _step("paper_days", label, reviewed >= SHORT_PROOF_DAYS_NEEDED, text,
                 value=f"{reviewed} of {SHORT_PROOF_DAYS_NEEDED}", seen="operator", enforced=True,
                 how="Short on Paper on three days; each day's refusals and fills are then yours to review.")


def _drill_steps(doc: dict[str, Any] | None, error: str | None) -> list[dict[str, Any]]:
    out = []
    for name in SHORT_PROOF_DRILLS:
        sid, label = f"drill_{name}", DRILL_LABELS[name]
        if doc is None:
            out.append(_step(sid, label, None, f"The proof could not be read ({error}).", enforced=True))
            continue
        drill = doc["drills"][name]
        if drill["passed"] is not None:
            run = drill["passed"]
            out.append(_step(sid, label, True, str(run.get("detail") or "Done."), enforced=True,
                             at=run.get("at")))
        elif drill["failed"]:
            run = drill["failed"][-1]
            out.append(_step(sid, label, False, f"Not passed yet: {run.get('detail')}. Run it again.",
                             enforced=True, how=DRILL_HOW[name], at=run.get("at")))
        else:
            out.append(_step(sid, label, False, "Not run yet.", enforced=True, how=DRILL_HOW[name]))
    return out


def _key_step() -> dict[str, Any]:
    from ibkr import safety

    if safety.short_enabled():
        return _step("live_key", "IBKR_SHORT_ENABLED", True, "IBKR_SHORT_ENABLED is on.", enforced=True)
    return _step("live_key", "IBKR_SHORT_ENABLED", False,
                 "IBKR_SHORT_ENABLED is off. You set it last, in .env, once everything above is done.", enforced=True,
                 seen="operator")


def view() -> dict[str, Any]:
    """``GET /api/short-proof``."""
    doc, error = store.read()
    complete, missing = status()
    count, total = done(doc)
    days = [{"date": day, "shorts": len(entry["orders"]), "symbols": entry["symbols"],
             "first_ts": entry.get("first_ts"), "last_ts": entry.get("last_ts"),
             "reviewed": (doc["reviews"].get(day) if SHORT_PROOF_REVIEW_OPEN else None)}
            for day, entry in sorted((doc or {}).get("days", {}).items(), reverse=True)]
    return {"schema_version": SHORT_PROOF_SCHEMA_VERSION, "generated_at": time.time(), "complete": complete,
            "missing": missing or None, "error": error, "done": count, "total": total,
            "steps": [_margin_step(), _reset_step(), _tests_step(), _days_step(doc, error),
                      *_drill_steps(doc, error), _key_step()],
            "days": days, "review": {"open": SHORT_PROOF_REVIEW_OPEN, "why": SHORT_PROOF_REVIEW_WAIT}}
