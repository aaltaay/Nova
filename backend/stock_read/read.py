"""Assemble the read for one symbol (ADR 036): gather the facts, derive the numbers, build the plan and
the seven groups, and summarize each group into one tile. ``derive`` and ``tiles`` are pure."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_stock_read import (
    STOCK_READ_MEDIAN_RANGE_BARS,
    STOCK_READ_PULL_WINDOW_SEC,
    STOCK_READ_SCHEMA_VERSION,
    STOCK_READ_VOLUME_PROFILE_BARS,
)
from scanner_wire import wire_safe
from stock_read import history, indicators, plan as plan_mod, rows, rows_trade

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
GROUPS = (
    ("in_play", "In play", "Is this a stock people are trading right now?"),
    ("setups", "Setups", "Is a playbook setup forming, and what is it waiting for?"),
    ("front", "Front side", "Is momentum still up, or is it fading?"),
    ("tape", "Tape", "What are Level 2 and the tape doing right now?"),
    ("short", "Short", "Can shorts press it? Tight borrow means fewer sellers."),
    ("float", "Float", "How many shares can trade?"),
    ("halts", "Halts", "What could stop me out or freeze me?"),
)
SHORT_NAMES = {"first_pullback": "Pullback", "bull_flag": "Flag", "flat_top_breakout": "Flat top",
               "red_to_green": "Red to green"}


def _lead_series(setups: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The scanner's own indicators: the bot's chosen setup's lane first (every lane reads the same
    minutes; a template may change the periods)."""
    ordered = sorted(setups, key=lambda s: 0 if s.get("chosen") else 1)
    return next((s["series"] for s in ordered if s.get("series")), None)


def derive(f: dict[str, Any]) -> dict[str, Any]:
    now = float(f["now"])
    facts = ((f.get("why") or {}).get("facts")) or {}
    allbars = f.get("bars") or []
    bars = indicators.session_of(allbars)
    price = facts.get("price") if facts.get("price") is not None else (bars[-1]["c"] if bars else None)
    change = facts.get("change_pct")
    prev_close = round(price / (1 + change), 4) if price is not None and change is not None and change > -1 else None
    setups = (f.get("setups") or {}).get("setups") or []
    series = _lead_series(setups)
    closes = [float(b["c"]) for b in allbars]
    if series:
        macd_1m = {"macd_hist": series["macd_hist"], "macd_line": series["macd_line"],
                   "macd_signal": series["macd_signal"]}
        macd_src = "the setup scanner's own 1-minute bars (what the gates read)"
        ema9, ema_src = series.get("ema"), "the setup scanner's own 1-minute bars"
    else:
        macd_1m = indicators.macd_last(closes)
        macd_src = "stored 1-minute bars (the scanner does not follow it)"
        ema9, ema_src = indicators.ema_last(closes, 9), "stored 1-minute bars"
    pulls = f.get("pulls") or {}
    bid_flags = [fl for fl in pulls.get("flags") or []
                 if fl.get("side") == "bid" and now - float(fl.get("ts") or 0) <= STOCK_READ_PULL_WINDOW_SEC]
    bot = f.get("bot") or {}
    return {
        "now": now, "price": price, "prev_close": prev_close, "change_pct": change, "bars": bars,
        "levels": indicators.levels(bars, price=price, prev_close=prev_close),
        "macd_1m": macd_1m, "macd_1m_source": macd_src,
        "macd_5m": indicators.macd_last([float(b["c"]) for b in f.get("bars5") or []]),
        "ema9": ema9, "ema20": indicators.ema_last(closes, 20), "ema_source": ema_src,
        "volume_profile": indicators.volume_profile(bars, STOCK_READ_VOLUME_PROFILE_BARS),
        "median_range": indicators.median_range(bars, STOCK_READ_MEDIAN_RANGE_BARS),
        "backside": indicators.backside(bars),
        "bid_pulls": len(bid_flags),
        "breakers": bot.get("breakers"),
    }


def _group(gid: str, label: str, question: str, group_rows: list[dict[str, Any]], verdict: str,
           value: str) -> dict[str, Any]:
    return {"id": gid, "label": label, "question": question, "verdict": verdict, "value": value, "rows": group_rows}


def _by_id(group_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in group_rows}


def tiles(f: dict[str, Any], d: dict[str, Any], plan: dict[str, Any] | None,
          hist: dict[str, Any] | None) -> list[dict[str, Any]]:
    built = {
        "in_play": rows.in_play_rows(f, hist),
        "setups": rows_trade.setup_rows(f, plan),
        "front": rows.front_rows(f, d),
        "tape": rows_trade.tape_rows(f, d, plan),
        "short": rows_trade.short_rows(f),
        "float": rows.float_rows(f),
        "halts": rows.halts_rows(f, d),
    }
    out = []
    for gid, label, question in GROUPS:
        verdict, value = _verdict(gid, built[gid], f, plan)
        out.append(_group(gid, label, question, built[gid], verdict, value))
    return out


def _verdict(gid: str, group_rows: list[dict[str, Any]], f: dict[str, Any],
             plan: dict[str, Any] | None) -> tuple[str, str]:
    r = _by_id(group_rows)
    states = [x["state"] for x in group_rows]
    if gid == "in_play":
        keys = ("hod_today", "catalyst", "why", "pillars", "rvol", "board")
        ok = sum(1 for k in keys if (r.get(k) or {}).get("state") == "ok")
        known = sum(1 for k in keys if (r.get(k) or {}).get("state") not in (None, "unknown"))
        if not known:
            return "unknown", "Not known"
        return ("ok", "Yes") if ok >= 4 else (("warn", "Partly") if ok >= 2 else ("bad", "No"))
    if gid == "setups":
        if not (f.get("setups") or {}).get("followed"):
            return "unknown", "Not followed"
        if plan and plan.get("source") == "setup":
            name = SHORT_NAMES.get(plan.get("setup_type") or "", "Setup")
            state = plan.get("state")
            return ("warn" if state == "forming" else "ok"), f"{name} {state}"
        return "info", "Nothing forming"
    if gid == "front":
        keys = ("macd_1m", "vwap", "ema", "volume_profile", "hod")
        ok = sum(1 for k in keys if (r.get(k) or {}).get("state") == "ok")
        bad = sum(1 for k in keys if (r.get(k) or {}).get("state") == "bad")
        if ok + bad == 0:
            return "unknown", "Not known"
        if bad == 0:
            return "ok", "Front side"
        return ("bad", "Back side") if bad >= 3 else ("warn", "Mixed")
    if gid == "tape":
        flow = (r.get("flow") or {}).get("value", "")
        if (r.get("spread") or {}).get("state") == "unknown" and (r.get("flow") or {}).get("state") == "unknown":
            return "unknown", "Blind"
        if flow.startswith("Flush"):
            return "bad", "Flush"
        if flow.startswith("Burst"):
            return "ok", "Burst"
        if (r.get("spread") or {}).get("state") == "bad":
            return "bad", "Wide"
        if (r.get("pulls") or {}).get("state") == "warn":
            return "warn", "Pulls"
        if (r.get("seller") or {}).get("state") in ("warn", "bad"):
            return "warn", "Seller"
        return "info", "Calm"
    if gid == "short":
        b = r.get("borrow") or {}
        if b.get("state") == "ok":
            return "ok", "No lend" if b.get("value", "").startswith("Nothing") else "HTB"
        if b.get("state") == "info":
            return "warn", "Easy"
        return "unknown", "Not known"
    if gid == "float":
        fl = r.get("float") or {}
        return fl.get("state") or "unknown", fl.get("value") or "Unknown"
    if gid == "halts":
        halted = r.get("halted") or {}
        if halted.get("state") == "bad":
            return "bad", "Halted"
        today = r.get("halts_today") or {}
        if today.get("state") == "warn":
            return "warn", today.get("value") or "Halts today"
        if halted.get("state") == "ok" and today.get("state") == "ok":
            return "ok", "No halts"
        return "unknown", "Not known"
    return ("unknown" if all(s == "unknown" for s in states) else "info"), ""


def build(f: dict[str, Any], *, entry: float | None = None, stop: float | None = None) -> dict[str, Any]:
    """The whole read from gathered facts (pure but for the daily-bar history cache)."""
    now = float(f["now"])
    d = derive(f)
    view = f.get("setups") or {}
    setups = view.get("setups") or []
    try:
        hist = history.summary(f["symbol"], now)
    except Exception:
        logger.warning("stock read: the daily history of %s could not be read", f["symbol"], exc_info=True)
        hist = None
    ctx = {"price": d["price"], "levels": d["levels"], "macd_hist": (d["macd_1m"] or {}).get("macd_hist"),
           "ema9": d["ema9"], "median_range": d["median_range"], "asks": (f.get("l2") or {}).get("asks") or [],
           "flow": f.get("flow"), "bid_pulls": d["bid_pulls"], "halted": f.get("halted"), "bars": d["bars"]}
    plan = plan_mod.build(setups, ctx, now=now, entry=entry, stop=stop)
    groups = tiles(f, d, plan, hist)
    counts = {k: 0 for k in ("ok", "warn", "bad", "unknown", "info")}
    for g in groups:
        for r in g["rows"]:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
    return wire_safe({
        "schema_version": STOCK_READ_SCHEMA_VERSION,
        "symbol": f["symbol"],
        "generated_at": now,
        "session_date": datetime.fromtimestamp(now, ET).date().isoformat(),
        "price": d["price"], "prev_close": d["prev_close"], "change_pct": d["change_pct"],
        "followed": bool(view.get("followed")), "followed_note": view.get("followed_note"),
        "setups": setups, "no_scanner": rows_trade.NO_SCANNER,
        "plan": plan, "levels": d["levels"], "groups": groups, "counts": counts,
    })
