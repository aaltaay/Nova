"""A short setup's grade (ADR 049 section 10): five pillars, read when it arms.

  run        ran ``min_run_pct`` or more today: the high of day over the prior close
  fade       faded ``min_fade_pct`` or more off the high: the price at arm under the high of day
  vwap       under the session VWAP at arm
  bad_news   dilution or bad news on file: the stock read's "Dilution on file" (a shelf, a 424B, an S-1, an
             8-K 3.02 -- ``stock_read.dilution_reader``, from memory) or today's catalyst verdict negative
  borrow     IBKR's shortable estimate (tick 236, cached) at least ``borrow_mult`` times the order: the desk
             sleeve's risk per trade over the setup's risk, cut to its max shares

A is all five known and passing, B four, C three or fewer -- the long grade's rule. A pillar Nova cannot read
is unknown (None), never a pass. The high of day and VWAP are the lane's own bars' (``Series``), the prior
close the host's (the board's, else the line's tick 9). A replay host knows neither the dilution reading nor
the borrow: those pillars are unknown there.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from constants_setups import SETUPS_GRADE_A, SETUPS_GRADE_B, SETUPS_GRADE_C

logger = logging.getLogger(__name__)

PILLARS = ("run", "fade", "vwap", "bad_news", "borrow")


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def grade(values: dict[str, Any], rules: Any) -> tuple[str, dict[str, bool | None]]:
    """A / B / C from the measured values (``run_pct``, ``fade_pct``, ``price``, ``vwap``, ``bad_news``,
    ``borrow``, ``order_shares``). Pure."""
    run, fade = _num(values.get("run_pct")), _num(values.get("fade_pct"))
    price, vwap = _num(values.get("price")), _num(values.get("vwap"))
    bad = values.get("bad_news") or {}
    dilution, negative = bad.get("dilution"), bad.get("negative")
    borrow = values.get("borrow") or {}
    shares, order = _num(borrow.get("shares")), _num(values.get("order_shares"))
    if dilution is True or negative is True:
        news: bool | None = True
    elif dilution is False and negative is False:
        news = False
    else:
        news = None
    checks: dict[str, bool | None] = {
        "run": None if run is None else run >= rules.min_run_pct - 1e-9,
        "fade": None if fade is None else fade >= rules.min_fade_pct - 1e-9,
        "vwap": None if price is None or vwap is None else price < vwap,
        "bad_news": news,
        "borrow": None if shares is None or not order else shares >= rules.borrow_mult * order - 1e-9,
    }
    passed = sum(1 for v in checks.values() if v)
    known = all(v is not None for v in checks.values())
    if known and passed == len(PILLARS):
        return SETUPS_GRADE_A, checks
    if passed == len(PILLARS) - 1:
        return SETUPS_GRADE_B, checks
    return SETUPS_GRADE_C, checks


def _order_shares(host: Any, risk: Any) -> int | None:
    """The sleeve's size for a setup risking ``risk`` a share (``LaneHost.order_shares``); None on a host
    without a sleeve (a replay)."""
    ask = getattr(host, "order_shares", None)
    if ask is None:
        return None
    try:
        return ask(_num(risk))
    except Exception:
        logger.warning("setup scanner: the sleeve's size could not be read", exc_info=True)
        return None


def _bad_news(host: Any, sym: str, now: float, pillars: dict[str, Any]) -> dict[str, Any]:
    """``{dilution, negative, text}``: the dilution reading (the host's, from memory) and today's verdict."""
    ask = getattr(host, "dilution", None)
    dilution, text = None, None
    if ask is not None:
        try:
            dilution, text = ask(sym, now)
        except Exception:
            logger.warning("setup scanner: %s's dilution reading could not be read", sym, exc_info=True)
    cat = pillars.get("catalyst")
    if not isinstance(cat, dict):
        negative = None
    else:
        negative = cat.get("verdict") == "negative" or bool(cat.get("negative_too"))
        if cat.get("verdict") == "negative" and cat.get("title"):
            text = text or f"negative news: {cat.get('title')}"
    return {"dilution": dilution, "negative": negative, "text": text}


def _borrow(host: Any, sym: str) -> dict[str, Any] | None:
    ask = getattr(host, "borrow", None)
    if ask is None:
        return None
    try:
        return ask(sym)
    except Exception:
        logger.warning("setup scanner: %s's borrow could not be read", sym, exc_info=True)
        return None


def graded(lane: Any, sym: str, now: float, pillars: dict[str, Any], risk: Any) -> dict[str, Any]:
    """``{grade, pillars}`` for a short lane's setup on ``sym`` now (pillars with their checks)."""
    det = lane.det.get(sym)
    s = getattr(det, "series", None)
    hod = s.hod[-1] if s is not None and s.hod else None
    vwap = s.vw[-1] if s is not None and s.vw else None
    prior = _num(((getattr(det, "context", None) or {}).get("prior_close")))
    price = _num(getattr(det, "last_price", None)) or _num(pillars.get("price"))
    if price is None and s is not None and s.c:
        price = s.c[-1]
    order = _order_shares(lane.host, risk)
    borrow = _borrow(lane.host, sym)
    values = {
        "run_pct": None if hod is None or not prior else round((hod / prior - 1.0) * 100.0, 2),
        "fade_pct": None if hod is None or price is None or hod <= 0 else round((hod - price) / hod * 100.0, 2),
        "price": price, "vwap": None if vwap is None else round(float(vwap), 4),
        "bad_news": _bad_news(lane.host, sym, now, pillars),
        "borrow": None if borrow is None else {**borrow, "order_shares": order}, "order_shares": order,
    }
    g, checks = grade(values, lane.p.grade)
    return {"grade": g, "pillars": {**pillars, "run_pct": values["run_pct"], "fade_pct": values["fade_pct"],
                                    "hod": hod, "vwap": values["vwap"], "prior_close": prior,
                                    "bad_news": values["bad_news"], "borrow": values["borrow"], "checks": checks}}
