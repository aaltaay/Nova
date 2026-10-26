"""The Congress page's overview, composed from what has been read (ADR 066; shape in architecture/schema/congress.md).

Pure over its inputs: the book's reports and trades, the roster, the kept portraits and the day. Periods are by
report date (since January 1, the last 90 or 30 days); a filter keeps a chamber, buys, sells, options, or trades
reported past the 45-day limit, and ``members`` keeps only those members (the Following tab). The last composition is
kept until something new is read, the roster changes or the day turns.
"""
from __future__ import annotations

import statistics
import threading
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from datetime import date, timedelta

from congress.constants_congress import (
    CONGRESS_ACTIVE_DAYS,
    CONGRESS_ACTIVE_WEEKS,
    CONGRESS_HOUSE_SEATS,
    CONGRESS_JUST_REPORTED,
    CONGRESS_LAG_BUCKET_DAYS,
    CONGRESS_LAG_BUCKETS,
    CONGRESS_LATE_DAYS,
    CONGRESS_MOST_ACTIVE,
    CONGRESS_MOST_TRADED,
    CONGRESS_PERIOD_DAYS,
    CONGRESS_PERIODS,
    CONGRESS_SENATE_SEATS,
    CONGRESS_TERRITORIES,
)
from congress.trades import Trade, tradable

_cache_lock = threading.Lock()
_cache: dict[tuple, dict] = {}


def member_wire(m: dict, photos: set[str]) -> dict:
    return {"bioguide": m["bioguide"], "name": m["name"], "party": m.get("party"), "caucus": m.get("caucus"),
            "state": m.get("state"), "district": m.get("district"), "chamber": m["chamber"],
            "current": bool(m.get("current")), "left": m.get("left"), "photo": m["bioguide"] in photos}


def period_from(period: str, today: date) -> str:
    if period == "ytd":
        return date(today.year, 1, 1).isoformat()
    return (today - timedelta(days=CONGRESS_PERIOD_DAYS[period])).isoformat()


def keep(filter_: str, members: frozenset[str] | None) -> Callable[[Trade], bool]:
    def ok(t: Trade) -> bool:
        if members is not None and t.bioguide not in members:
            return False
        if filter_ in ("house", "senate"):
            return t.chamber == filter_
        if filter_ == "buys":
            return t.side == "buy" and not t.gift
        if filter_ == "sells":
            return t.side == "sell" and not t.gift
        if filter_ == "options":
            return t.kind == "option"
        if filter_ == "late":
            return t.late
        return True
    return ok


def _paper_counts(filter_: str, chamber: str) -> bool:
    """A paper or unread report holds trades nobody read: it can only count under a chamber or all."""
    return filter_ == "all" or filter_ == chamber


def report_read(report: dict) -> bool:
    return report["kind"] == "electronic" and report.get("read_at") is not None and not report.get("error")


def seats(roster: list[dict], reports: dict[str, dict], photos: set[str]) -> dict:
    current = [m for m in roster if m.get("current")]
    senate = [member_wire(m, photos) for m in current if m["chamber"] == "senate"]
    house = [member_wire(m, photos) for m in current if m["chamber"] == "house" and m.get("state") not in CONGRESS_TERRITORIES]
    delegates = [member_wire(m, photos) for m in current if m["chamber"] == "house" and m.get("state") in CONGRESS_TERRITORIES]
    filed = {r["bioguide"] for r in reports.values() if r.get("bioguide")}
    former = sorted((member_wire(m, photos) for m in roster if not m.get("current") and m["bioguide"] in filed),
                    key=lambda m: m.get("left") or "", reverse=True)
    return {"senate": senate, "house": house, "delegates": delegates, "former": former,
            "empty": {"senate": max(0, CONGRESS_SENATE_SEATS - len(senate)), "house": max(0, CONGRESS_HOUSE_SEATS - len(house))}}


def reported(reports: dict[str, dict], trades: list[Trade], ok, filter_: str, members, since: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in trades:
        if t.bioguide and t.filed >= since and ok(t):
            out[t.bioguide] = "trades"
    for r in reports.values():
        bio = r.get("bioguide")
        if (not bio or bio in out or r.get("amended_by") or (members is not None and bio not in members)
                or (r.get("amends") or r["filed"]) < since):
            continue
        if not report_read(r) and _paper_counts(filter_, r["chamber"]):
            out[bio] = "paper"
    return out


def just_reported(reports: dict[str, dict], by_report: dict[str, list[Trade]], ok, filter_: str, members,
                  roster: dict[str, dict], photos: set[str]) -> list[dict]:
    out = []
    for r in sorted(reports.values(), key=lambda r: (r["filed"], r["id"]), reverse=True):
        if members is not None and r.get("bioguide") not in members:
            continue
        mine = [t for t in by_report.get(r["id"], ()) if ok(t)]
        read = report_read(r)
        if read and not mine:
            continue
        if not read and not _paper_counts(filter_, r["chamber"]):
            continue
        top = max(mine, key=lambda t: (tradable(t), t.low or 0)) if mine else None
        m = roster.get(r.get("bioguide") or "")
        out.append({"id": r["id"], "chamber": r["chamber"], "member": member_wire(m, photos) if m else None,
                    "filer": r.get("filer_name"), "filed": r["filed"], "kind": r["kind"], "read": read, "url": r["url"],
                    "amends": r.get("amends"), "trades": len(by_report.get(r["id"], ())),
                    "top": None if top is None else {"ticker": top.ticker, "asset": top.asset, "side": top.side,
                                                     "kind": top.kind, "gift": top.gift, "amount": top.amount,
                                                     "lag_days": top.lag_days}})
        if len(out) >= CONGRESS_JUST_REPORTED:
            break
    return out


def most_traded(trades: Iterable[Trade], since: str, ok) -> list[dict]:
    groups: dict[str, dict] = {}
    for t in trades:
        if t.filed < since or not ok(t) or not tradable(t):
            continue
        g = groups.setdefault(t.ticker, {"ticker": t.ticker, "assets": Counter(), "buyers": set(), "sellers": set(),
                                         "who": set(), "buys": 0, "sells": 0})
        g["assets"][t.asset] += 1
        g["who"].add(t.bioguide or f"?{t.filer}")
        if t.side == "buy":
            g["buys"] += 1
            if t.bioguide:
                g["buyers"].add(t.bioguide)
        else:
            g["sells"] += 1
            if t.bioguide:
                g["sellers"].add(t.bioguide)
    ranked = sorted(groups.values(), key=lambda g: (-len(g["who"]), -(g["buys"] + g["sells"]), g["ticker"]))
    return [{"ticker": g["ticker"], "asset": g["assets"].most_common(1)[0][0], "members": len(g["who"]),
             "buyers": sorted(g["buyers"]), "sellers": sorted(g["sellers"]), "buys": g["buys"], "sells": g["sells"]}
            for g in ranked[:CONGRESS_MOST_TRADED]]


def weeks(trades: Iterable[Trade], today: date, n: int) -> dict:
    start = today - timedelta(days=7 * n - 1)
    buy, sell = [0] * n, [0] * n
    for t in trades:
        try:
            i = (date.fromisoformat(t.tx) - start).days // 7
        except ValueError:
            continue
        if 0 <= i < n and not t.gift:
            if t.side == "buy":
                buy[i] += 1
            elif t.side == "sell":
                sell[i] += 1
    return {"from": start.isoformat(), "buy": buy, "sell": sell}


def most_active(trades: list[Trade], today: date, ok, roster: dict[str, dict], photos: set[str]) -> list[dict]:
    since = (today - timedelta(days=CONGRESS_ACTIVE_DAYS)).isoformat()
    mine: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        if t.bioguide and t.filed >= since and ok(t):
            mine[t.bioguide].append(t)
    out = []
    for bio, ts in sorted(mine.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        m = roster.get(bio)
        if m is None:
            continue
        lags = [t.lag_days for t in ts if t.lag_days is not None]
        tops = Counter(t.ticker for t in ts if tradable(t)).most_common(3)
        out.append({**member_wire(m, photos), "trades": len(ts),
                    "buys": sum(t.side == "buy" and not t.gift for t in ts),
                    "sells": sum(t.side == "sell" and not t.gift for t in ts),
                    "median_lag_days": statistics.median(lags) if lags else None,
                    "late": sum(t.late for t in ts), "weeks": weeks(ts, today, CONGRESS_ACTIVE_WEEKS),
                    "top": [k for k, _ in tops]})
        if len(out) >= CONGRESS_MOST_ACTIVE:
            break
    return out


def lag(trades: Iterable[Trade]) -> dict:
    lags = [t.lag_days for t in trades if t.lag_days is not None and t.lag_days >= 0]
    buckets = [0] * CONGRESS_LAG_BUCKETS
    for x in lags:
        buckets[min(x // CONGRESS_LAG_BUCKET_DAYS, CONGRESS_LAG_BUCKETS - 1)] += 1
    n = len(lags)
    return {"bucket_days": CONGRESS_LAG_BUCKET_DAYS, "buckets": buckets, "limit_days": CONGRESS_LATE_DAYS, "trades": n,
            "median_days": statistics.median(lags) if n else None,
            "within_week_pct": round(100 * sum(x <= 7 for x in lags) / n, 1) if n else None,
            "after_limit_pct": round(100 * sum(x > CONGRESS_LATE_DAYS for x in lags) / n, 1) if n else None}


def counts(trades: list[Trade], since: str) -> dict:
    ytd = [t for t in trades if t.filed >= since]
    return {f: sum(1 for t in ytd if keep(f, None)(t)) for f in ("all", "house", "senate", "buys", "sells", "options", "late")}


def compose(version: int, reports: dict[str, dict], trades: list[Trade], roster_list: list[dict], photos: set[str],
            today: date, filter_: str = "all", members: frozenset[str] | None = None, roster_at: float | None = None) -> dict:
    """The composed blocks (everything but the parts that change every second: consent, sources, generated_at)."""
    key = (version, filter_, members, today, roster_at, len(photos))
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    ok = keep(filter_, members)
    roster = {m["bioguide"]: m for m in roster_list}
    by_report: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        by_report[t.report].append(t)
    froms = {p: period_from(p, today) for p in CONGRESS_PERIODS}
    ytd = froms["ytd"]
    out = {"today": today.isoformat(), "year": today.year, "periods": {p: {"from": f} for p, f in froms.items()},
           "counts": counts(trades, ytd), "seats": seats(roster_list, reports, photos),
           "reported": {p: reported(reports, trades, ok, filter_, members, f) for p, f in froms.items()},
           "just_reported": just_reported(reports, by_report, ok, filter_, members, roster, photos),
           "most_traded": {p: most_traded(trades, f, ok) for p, f in froms.items()},
           "most_active": most_active(trades, today, ok, roster, photos),
           "lag": lag(t for t in trades if t.filed >= ytd and ok(t))}
    with _cache_lock:
        if len(_cache) > 32:
            _cache.clear()
        _cache[key] = out
    return out


def source_counts(reports: dict[str, dict], trades: list[Trade], chamber: str) -> dict:
    mine = [r for r in reports.values() if r["chamber"] == chamber]
    return {"reports": len(mine), "electronic": sum(r["kind"] == "electronic" for r in mine),
            "paper": sum(r["kind"] == "paper" for r in mine),
            "unread": sum(r["kind"] == "electronic" and not report_read(r) for r in mine),
            "trades": sum(1 for t in trades if t.chamber == chamber)}


def reset_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
