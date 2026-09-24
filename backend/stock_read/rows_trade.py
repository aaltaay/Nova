"""The read's rows for the trade itself (ADR 035): the setups, the tape and book, the short side.
Pure; rows are ``stock_read.rows.row`` shaped."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_setups import (
    TAPE_GATE_BIG_SELLER_SHARES,
    TAPE_GATE_SPREAD_MAX_DOLLARS,
    TAPE_GATE_SPREAD_MAX_PCT,
    TAPE_GATE_WALL_SHARES,
)
from constants_stock_read import (
    STOCK_READ_BORROW_HTB_FEE_PCT,
    STOCK_READ_PULL_WINDOW_SEC,
    STOCK_READ_SI_HIGH_SHARE,
)
from stock_read.plan import setup_name
from stock_read.rows import hhmm, row, shares

ET = ZoneInfo("America/New_York")
LEVEL_NAMES = {0: "Off", 1: "Eyes", 2: "Strategy"}
NO_SCANNER = [
    {"setup_type": "gap_and_go", "label": "Gap and Go", "reason": "No scanner yet: only its level is drawn (the "
     "premarket high)."},
    {"setup_type": "micro_pullback", "label": "Micro pullback", "reason": "Parked: it needs one-second bars."},
]


def _lane_value(lane: dict[str, Any]) -> tuple[str, str]:
    """``(value, state)`` for a lane's row, in the scanner's own words."""
    state, reason = lane.get("state"), lane.get("reason") or ""
    setup = lane.get("setup") or {}
    if state == "near":
        dist = lane.get("distance")
        return (f"Near · {dist:.2f} under {setup.get('trigger')}" if dist is not None else "Near the trigger"), "ok"
    if state == "armed":
        return f"Armed · trigger {setup.get('trigger')}", "ok"
    if state == "triggered":
        return f"Triggered at {setup.get('trigger_price') or setup.get('trigger')}", "ok"
    if state == "filtered":
        return f"Filtered · {reason.replace('filtered: ', '')}", "warn"
    if state == "failed":
        return f"Failed · {reason}", "bad"
    if state in ("leg", "pullback"):
        return ("Forming" if state == "leg" else "Blocked") + f" · {reason}", "warn"
    return f"Watching · {reason}", "info"


def setup_rows(f: dict[str, Any], plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    view = f.get("setups") or {}
    out: list[dict[str, Any]] = []
    src = "The setup scanner's lanes (the template in play)"
    if not view.get("followed"):
        out.append(row("scanner", "Setup scanner", "Not followed", "unknown", src,
                       view.get("followed_note") or "The setup scanner could not be read"))
    for lane in view.get("setups") or []:
        value, state = _lane_value(lane)
        name = setup_name(lane.get("setup_type"))
        label = name[:1].upper() + name[1:] + (" (bot's pick)" if lane.get("chosen") else "")
        forming = lane.get("forming") or {}
        bits = []
        if forming.get("waiting"):
            bits.append(f"It arms after {forming['waiting']}.")
        if forming.get("blocked") and forming.get("blocked") not in value:
            bits.append(f"Blocked: {forming['blocked']}.")
        if forming:
            bits.append(f"Would arm at trigger {forming['trigger']}, stop {forming['stop']}, risk {forming['risk']:.2f}.")
        leg = lane.get("leg") or {}
        if leg.get("high") and lane.get("state") in ("leg", "pullback", "armed", "near"):
            bits.append(f"Leg {leg.get('low')} -> {leg.get('high')} ({(leg.get('pct') or 0) * 100:.1f}%).")
        out.append(row(f"lane_{lane.get('setup_type')}", label, value, state, src, " ".join(bits) or None))
    for ns in NO_SCANNER:
        out.append(row(f"lane_{ns['setup_type']}", ns["label"], "No scanner yet" if ns["setup_type"] == "gap_and_go"
                       else "Parked", "info", "--", ns["reason"]))
    tape = (plan or {}).get("tape")
    if tape and tape.get("verdict"):
        verdict = str(tape["verdict"])
        out.append(row("tape_gate", "Tape at the trigger", verdict.upper(),
                       {"go": "ok", "wait": "warn", "veto": "bad"}.get(verdict, "unknown"), "The setup's tape gate",
                       "; ".join(tape.get("reasons") or []) or None))
    else:
        line = (f.get("bot") or {}).get("depth_line")
        out.append(row("tape_gate", "Tape at the trigger", "Not read yet", "info" if line else "unknown",
                       "The setup's tape gate",
                       "The tape gate reads a setup only while it is armed or near." + (
                           "" if line else " Nova also holds no Level 2 line for it: open its Level 2 or record it.")))
    out.append(_bot_row(f.get("bot")))
    return out


def _bot_row(bot: dict[str, Any] | None) -> dict[str, Any]:
    src = "The bot's session"
    if not bot:
        return row("bot", "The bot on it", "Not known", "unknown", src, "The bot session could not be read")
    level = LEVEL_NAMES.get(int(bot.get("level") or 0), str(bot.get("level")))
    value = f"{level} · {'active' if bot.get('active') else 'not active'}"
    missing = [w for w, ok in (("not on its allowlist", bot.get("allowlisted")),
                               ("no Level 2 line held", bot.get("depth_line"))) if not ok]
    trade = bot.get("trade")
    detail = (f"Its pick: {setup_name(bot.get('chosen'))}. " +
              (f"It cannot fire here: {', '.join(missing)}. " if missing else "Allowlisted with a depth line. ") +
              (f"Its trade: {trade.get('state')} {trade.get('qty')} @ {trade.get('entry_fill_price') or trade.get('entry_planned')}."
               if trade else "No bot trade on it."))
    return row("bot", "The bot on it", value, "warn" if missing else "info", src, detail)


# -- tape and book ------------------------------------------------------------------------------------
def tape_rows(f: dict[str, Any], d: dict[str, Any], plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    sym = f.get("symbol")
    l2 = f.get("l2")
    no_line = f"Nova holds no Level 2 line for {sym}: open its Level 2 or record it."
    out: list[dict[str, Any]] = []
    price = d.get("price")
    if not l2:
        out.append(row("spread", "Spread", "Not known", "unknown", "Level 2", no_line))
        out.append(row("book", "Book balance (top 5)", "Not known", "unknown", "Level 2", no_line))
    else:
        spread = l2.get("spread_dollars")
        bids, asks = l2.get("bids") or [], l2.get("asks") or []
        if spread is None or not bids or not asks:
            out.append(row("spread", "Spread", "Not known", "unknown", "Level 2", "The book has no bid or no ask"))
        else:
            bid, ask = float(bids[0]["price"]), float(asks[0]["price"])
            limit = max(TAPE_GATE_SPREAD_MAX_DOLLARS, TAPE_GATE_SPREAD_MAX_PCT * (price or ask))
            out.append(row("spread", "Spread", f"{spread:.2f} · {bid:.2f} x {ask:.2f} ({spread / ask:.1%})",
                           "ok" if spread <= limit + 1e-9 else "bad", "Level 2",
                           f"The tape gate vetoes a spread wider than {limit:.2f}."))
        bt, at = l2.get("bid_total"), l2.get("ask_total")
        if bt is not None and at is not None:
            ratio = (bt / at) if at else None
            side = "bid-heavy" if (ratio or 0) >= 1 else "ask-heavy"
            out.append(row("book", "Book balance (top 5)", f"bids {int(bt):,} vs asks {int(at):,}", "info", "Level 2",
                           f"{side} {ratio:.1f}x" if ratio else None))
    flow = f.get("flow")
    if not flow or flow.get("label") in (None, "blind"):
        out.append(row("flow", "Tape flow", "Not known", "unknown", "The tape flow score (-1 sellers .. +1 buyers)",
                       no_line if not l2 else "No prints and no book to score yet"))
    else:
        label, score = str(flow.get("label")), flow.get("score")
        state = {"burst": "ok", "flush": "bad", "neutral": "info", "quiet": "info"}.get(label, "info")
        value = label.title() + (f" ({score:+.2f})" if score is not None else "")
        out.append(row("flow", "Tape flow", value, state, "The tape flow score (-1 sellers .. +1 buyers)",
                       "A flush after a rise has been followed by a further drop in Nova's recordings (ADR 034)."
                       if label == "flush" else None))
    out.extend(_pull_rows(f.get("pulls"), f.get("now") or 0.0, no_line))
    out.append(_seller_row(l2, price, plan, no_line))
    ppm = f.get("prints_per_min")
    out.append(row("prints", "Prints", f"{ppm} in the last minute" if ppm is not None else "Not known",
                   "info" if ppm is not None else "unknown", "The tape ring",
                   None if ppm is not None else "No tape line is reaching Nova for it"))
    return out


def _pull_rows(pulls: dict[str, Any] | None, now: float, no_line: str) -> list[dict[str, Any]]:
    src = "The book watcher (hints consistent with spoofing -- never a detection)"
    if not pulls or not pulls.get("watching"):
        return [row("pulls", "Pulled orders", "Not known", "unknown", src, no_line)]
    flags = [fl for fl in pulls.get("flags") or [] if now - float(fl.get("ts") or 0) <= STOCK_READ_PULL_WINDOW_SEC]
    bid_flags = [fl for fl in flags if fl.get("side") == "bid"]
    out = [row("pulls", "Pulled orders",
               f"{len(flags)} flag{'s' if len(flags) != 1 else ''} in the last minute" if flags else "No flags",
               "warn" if bid_flags else "info", src, (flags[-1].get("why") if flags else None), None)]
    ps, fs = pulls.get("pulled_shares"), pulls.get("filled_shares")
    if ps is not None and fs is not None:
        out.append(row("pulled_filled", "Pulled vs filled", f"{shares(ps)} pulled · {shares(fs)} filled",
                       "warn" if ps > 3 * max(fs, 1) else "info", src,
                       f"{pulls.get('pulls')} pulls, {pulls.get('fills')} fills, {pulls.get('large_pulls')} large "
                       f"over {int(pulls.get('window_sec') or 60)} s"))
    return out


def _seller_row(l2: dict[str, Any] | None, price: float | None, plan: dict[str, Any] | None,
                no_line: str) -> dict[str, Any]:
    src = "Level 2 (the tape gate's wall sizes)"
    if not l2:
        return row("seller", "Seller ahead", "Not known", "unknown", src, no_line)
    lo = (plan or {}).get("entry") or price
    hi = (plan or {}).get("target")
    asks = [a for a in l2.get("asks") or [] if lo is not None and float(a["price"]) >= lo - 1e-9
            and (hi is None or float(a["price"]) <= hi + 1e-9)]
    if not asks:
        return row("seller", "Seller ahead", "No asks in view", "info", src)
    big = max(asks, key=lambda a: float(a.get("size") or 0))
    size = float(big.get("size") or 0)
    where = "between entry and target" if hi is not None else "over the price"
    if size >= TAPE_GATE_WALL_SHARES:
        return row("seller", "Seller ahead", f"{int(size):,} at {float(big['price']):.2f}",
                   "bad" if size >= TAPE_GATE_BIG_SELLER_SHARES else "warn", src, f"The largest ask {where}.")
    return row("seller", "Seller ahead", f"None of {TAPE_GATE_WALL_SHARES // 1000}K+", "ok", src,
               f"The largest ask {where}: {int(size):,} at {float(big['price']):.2f} (top 10 levels in view).")


# -- short side ---------------------------------------------------------------------------------------
def short_rows(f: dict[str, Any]) -> list[dict[str, Any]]:
    facts = ((f.get("why") or {}).get("facts")) or {}
    out = [_borrow_row(facts.get("borrow"))]
    snap = f.get("shortable")
    src = "IBKR shortable shares (tick 236)"
    if not snap or snap.get("state") == "unknown":
        out.append(row("shortable", "Shortable (IBKR)", "Unknown", "unknown", src,
                       "IBKR has not answered for it; the Trader's Level 2 asks again every minute."))
    else:
        state = snap["state"]
        value = {"htb_likely": "Hard to borrow", "thin": "Thin", "shortable_est": "Shortable"}.get(state, state)
        out.append(row("shortable", "Shortable (IBKR)", value + (" (stale)" if snap.get("stale") else ""),
                       "ok" if state in ("htb_likely", "thin") else "info", src,
                       f"~{int(snap['shortable_shares']):,} shares" if isinstance(snap.get("shortable_shares"), (int, float))
                       and snap["shortable_shares"] > 0 else None, snap.get("fetched_at")))
    si, fl = facts.get("short_interest"), facts.get("float_shares")
    if si is None:
        out.append(row("short_interest", "Short interest", "Unknown", "unknown", "FINRA via Yahoo", "Yahoo gave none"))
    else:
        share = (si / fl) if fl else facts.get("short_pct_float")
        value = f"{shares(si)} shares" + (f" · {share:.0%} of float" if share is not None else "")
        dtc = facts.get("days_to_cover")
        out.append(row("short_interest", "Short interest", value,
                       "ok" if share is not None and share >= STOCK_READ_SI_HIGH_SHARE else "info", "FINRA via Yahoo",
                       "; ".join(bit for bit in (
                           f"FINRA settlement {_day(facts['short_interest_ts'])}" if facts.get("short_interest_ts") else None,
                           f"Yahoo ratio {dtc:.1f} days" if dtc is not None else None) if bit) or None,
                       facts.get("short_interest_ts")))
    out.append(row("ssr", "Short-sale restriction", "Not tracked", "unknown", "--",
                   "Nova does not read the listing exchange's short-sale-restriction list yet."))
    return out


def _day(ts: float) -> str:
    dt = datetime.fromtimestamp(float(ts), ET)
    return f"{dt:%b} {dt.day}"


def _borrow_row(b: dict[str, Any] | None) -> dict[str, Any]:
    src = "IBKR's short-stock file (every 15 min)"
    if not b:
        return row("borrow", "Borrow (IBKR)", "Not known", "unknown", src, "The borrow file has not been read yet")
    open_ = b.get("open") or {}
    hist = ""
    if open_.get("fee_rate") is not None:
        hist = f"At {hhmm(open_.get('as_of'))}: fee {open_['fee_rate']:.1f}%/yr, {shares(open_.get('available'))} to lend."
    if not b.get("listed") or (b.get("available") is not None and b["available"] <= 0):
        return row("borrow", "Borrow (IBKR)", "Nothing to lend", "ok", src, hist or None, b.get("as_of"))
    fee = b.get("fee_rate")
    if fee is not None and fee >= STOCK_READ_BORROW_HTB_FEE_PCT:
        return row("borrow", "Borrow (IBKR)", f"Hard to borrow · fee {fee:.1f}%/yr", "ok", src,
                   f"{shares(b.get('available'))} to lend. {hist}".strip(), b.get("as_of"))
    return row("borrow", "Borrow (IBKR)", f"Easy · fee {fee or 0:.1f}%/yr · {shares(b.get('available'))} to lend",
               "info", src, hist or None, b.get("as_of"))
