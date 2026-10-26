"""The Congress page's other reads (ADR 066): every member, one member's trades, one stock's trades. Pure.

Shapes in architecture/schema/congress.md ("Routes"). "This year" is by report date, since January 1 (Eastern).
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import date

from congress.board import member_wire, report_read, weeks
from congress.constants_congress import CONGRESS_MEMBER_WEEKS, CONGRESS_TICKER_MAX_TRADES
from congress.trades import Trade, tradable, wire


def _ytd_stats(ts: list[Trade], rs: list[dict], since: str) -> dict:
    year = [t for t in ts if t.filed >= since]
    lags = [t.lag_days for t in year if t.lag_days is not None]
    yr = [r for r in rs if (r.get("amends") or r["filed"]) >= since]
    return {"ytd": {"trades": len(year), "buys": sum(t.side == "buy" and not t.gift for t in year),
                    "sells": sum(t.side == "sell" and not t.gift for t in year), "reports": len(yr),
                    "paper": sum(not report_read(r) for r in yr)},
            "last_filed": max((r["filed"] for r in rs), default=None),
            "median_lag_days": statistics.median(lags) if lags else None,
            "late": sum(t.late for t in year)}


def members(reports: dict[str, dict], trades: list[Trade], roster: list[dict], photos: set[str], today: date) -> list[dict]:
    since = date(today.year, 1, 1).isoformat()
    by_member_t: dict[str, list[Trade]] = {}
    for t in trades:
        if t.bioguide:
            by_member_t.setdefault(t.bioguide, []).append(t)
    by_member_r: dict[str, list[dict]] = {}
    for r in reports.values():
        if r.get("bioguide"):
            by_member_r.setdefault(r["bioguide"], []).append(r)
    out = []
    for m in roster:
        if not m.get("current") and m["bioguide"] not in by_member_r:
            continue                                 # someone who left and never reported in what we keep
        stats = _ytd_stats(by_member_t.get(m["bioguide"], []), by_member_r.get(m["bioguide"], []), since)
        out.append({**member_wire(m, photos), "committees": m.get("committees", []), **stats})
    out.sort(key=lambda x: (-x["ytd"]["trades"], x["name"]))
    return out


def member(bioguide: str, reports: dict[str, dict], trades: list[Trade], roster: dict[str, dict], photos: set[str],
           today: date) -> dict | None:
    m = roster.get(bioguide)
    if m is None:
        return None
    mine_t = [t for t in trades if t.bioguide == bioguide]
    mine_r = sorted((r for r in reports.values() if r.get("bioguide") == bioguide),
                    key=lambda r: (r["filed"], r["id"]), reverse=True)
    stats = _ytd_stats(mine_t, mine_r, date(today.year, 1, 1).isoformat())
    return {"member": {**member_wire(m, photos), "committees": m.get("committees", []), **stats},
            "weeks": weeks(mine_t, today, CONGRESS_MEMBER_WEEKS),
            "trades": [wire(t) for t in mine_t],
            "reports": [{"id": r["id"], "chamber": r["chamber"], "filed": r["filed"], "kind": r["kind"],
                         "read": report_read(r), "error": r.get("error"), "url": r["url"], "amends": r.get("amends"),
                         "amended_by": r.get("amended_by"), "trades": r.get("trades") or 0} for r in mine_r]}


def ticker(symbol: str, trades: list[Trade], roster: dict[str, dict], photos: set[str]) -> dict:
    mine = [t for t in trades if t.ticker == symbol][:CONGRESS_TICKER_MAX_TRADES]
    assets = Counter(t.asset for t in mine)
    out = []
    for t in mine:
        m = roster.get(t.bioguide or "")
        out.append({**wire(t), "member": member_wire(m, photos) if m else None})
    return {"ticker": symbol, "asset": assets.most_common(1)[0][0] if assets else None,
            "buyers": sorted({t.bioguide for t in mine if t.bioguide and tradable(t) and t.side == "buy"}),
            "sellers": sorted({t.bioguide for t in mine if t.bioguide and tradable(t) and t.side == "sell"}),
            "trades": out}
