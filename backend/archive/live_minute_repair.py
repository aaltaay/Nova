"""Correct the stored live minutes master's builder got wrong, from the L1 tick archive.

Two defects wrote ``bars_intraday`` live rows (``source='ibkr_l1'``) that the tape never printed:

- **Cut down** (before PR #1273): ``ibkr/l1_minute`` let go of a minute once the desk's clock wrote it,
  so the next update stamped in it opened a bucket holding only itself, and that write replaced the
  minute's volume with its last update or two's shares.
- **Phantom shares**: a lower day volume on the line was taken as a new baseline, so each return to the
  real total counted again (a second counter or a stale figure on 2,949 of 19,984 streamed symbol-days;
  10^6-scaled totals on 2026-09-18 / 09-21).

``l1_ticks`` keeps the updates the builder read -- the streaming line, stamped with IBKR's whole second;
the table reprice also writes there, on the desk's own clock, and is left out. Each minute is counted by
both rules: master's, to recognise what it wrote, and the builder's own now (``volume_increment``). A
stored row moves only when it carries one of the two fingerprints: its volume is the shares of the
minute's last few updates by master's rule (``fragment``), or it is master's whole count while the
builder's now is different (``phantom``). Master also counted the lastSize of each update it took as a
baseline, which the archive does not keep, so a match may sit up to ``LASTSIZE_SLACK`` a drop above
master's count. The row is then set to the builder's count. Everything else stays: already the builder's
count, a value that matches neither (a restart's baseline inside the minute), no ticks, or a minute so
recent that a running builder may still write it. A minute whose first update follows ``GAP_SEC`` of
silence (a restart, or a line that dropped out of the budget and came back) may only come down: its count
holds the shares traded while the line was away, and a raise would land them on that one minute. Scored
against Massive's consolidated tape, the repaired live minutes of six stock-days held 96-106% of their
volume (13-134% as stored). IBKR's own history rows are never touched.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from constants import ARCHIVE_SOURCE_IBKR_L1
from ibkr.l1_minute import volume_increment
from market import in_trading_session

ET = ZoneInfo("America/New_York")
GAP_SEC = 60.0
LASTSIZE_SLACK = 10_000.0
RECENT_SKIP_SEC = 900.0
SCHEMA_VERSION = 1
KINDS = ("whole", "fragment", "phantom", "other", "gap", "no_ticks", "recent")


@dataclass(frozen=True)
class Change:
    symbol: str
    ts: float
    stored: float
    volume: float


@dataclass
class MinuteCounts:
    master: list[float] = field(default_factory=list)   # master's rule: a lower total was a new baseline
    fixed: list[float] = field(default_factory=list)    # the builder's rule now
    drops: list[bool] = field(default_factory=list)     # master took the update as a baseline (and added its lastSize)
    after_gap: bool = False


@dataclass
class DayPlan:
    day: str
    kinds: Counter = field(default_factory=Counter)
    changes: list[Change] = field(default_factory=list)

    @property
    def shares_added(self) -> float:
        return sum(max(0.0, c.volume - c.stored) for c in self.changes)

    @property
    def shares_removed(self) -> float:
        return sum(max(0.0, c.stored - c.volume) for c in self.changes)


def _master_increment(prior: float | None, day_volume: float | None) -> tuple[float, float | None, bool]:
    """Master's ``volume_increment``, and whether it took a lower total as a new baseline. Master also counted
    that update's lastSize there, which the archive does not keep (``LASTSIZE_SLACK`` stands for it)."""
    if day_volume is None or day_volume < 0:
        return 0.0, prior, False
    cum = float(day_volume)
    if prior is None:
        return 0.0, cum, False
    if cum < prior:
        return 0.0, cum, True
    return cum - prior, cum, False


def minute_counts(ticks: Iterable[tuple[float, float | None]]) -> dict[float, MinuteCounts]:
    """Each minute's increments by both rules, in arrival order, from one symbol-day's ``(ts, day_volume)``.

    An update stamped before the newest minute goes where each builder put it: the builder now counts its
    shares in the newest minute (``l1_minute.on_last``); master dropped them, its baseline moved on.
    """
    out: dict[float, MinuteCounts] = {}
    master = fixed = None
    last_ts: float | None = None
    newest: float | None = None
    for ts, day_volume in ticks:
        ts = float(ts)
        if ts != int(ts):
            continue
        if not in_trading_session(ts):
            master = fixed = last_ts = None
            continue
        stamped = float(int(ts // 60) * 60)
        newest = stamped if newest is None else max(newest, stamped)
        minute = out.setdefault(newest, MinuteCounts())
        if last_ts is not None and ts - last_ts > GAP_SEC:
            minute.after_gap = True
        last_ts = ts if last_ts is None else max(last_ts, ts)
        increment, fixed = volume_increment(fixed, size=None, cum_volume=day_volume)
        minute.fixed.append(increment)
        increment, master, dropped = _master_increment(master, day_volume)
        if stamped == newest:
            minute.master.append(increment)
            minute.drops.append(dropped)
    return out


def classify(stored: float, counts: MinuteCounts) -> tuple[str, float]:
    """``(kind, volume)``: ``fragment`` and ``phantom`` take the builder's count, the rest keep ``stored``.

    Where master took a lower total as a baseline it added that update's lastSize, so a match may sit up to
    ``LASTSIZE_SLACK`` a drop above master's count (exact when there was none). ``phantom`` is master's whole
    count told apart from the builder's by more than that slack: it comes down where master counted a second
    counter's return, and goes up where master dropped an update stamped before the newest minute. A minute
    after a silence only comes down: its count holds the shares traded while the line was away, and a raise
    would land them on this minute.
    """
    now = round(sum(counts.fixed))
    master = round(sum(counts.master))
    have = round(float(stored))
    slack = LASTSIZE_SLACK * sum(counts.drops)
    phantom = abs(master - now) > slack and master <= have <= master + slack
    if have == now:
        return "whole", float(stored)
    if counts.after_gap:
        return ("phantom", float(now)) if phantom and now < have else ("gap", float(stored))
    if 0 < have < master:
        tail, tail_drops = 0.0, 0
        for increment, dropped in zip(reversed(counts.master[1:]), reversed(counts.drops[1:]), strict=True):
            tail += increment
            tail_drops += dropped
            if 0 <= have - round(tail) <= LASTSIZE_SLACK * tail_drops:
                return "fragment", float(now)
    if phantom:
        return "phantom", float(now)
    return "other", float(stored)


def _day_bounds(day: str) -> tuple[float, float]:
    start = datetime.fromisoformat(day).replace(tzinfo=ET)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def live_days(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Session date -> symbols with stored live 1Min rows (one pass over ``bars_intraday``)."""
    days: dict[str, list[str]] = {}
    for symbol, day in conn.execute(
        "SELECT DISTINCT symbol, session_date FROM bars_intraday WHERE timeframe = '1Min' AND source = ?",
        (ARCHIVE_SOURCE_IBKR_L1,),
    ):
        days.setdefault(str(day), []).append(str(symbol))
    return {day: sorted(symbols) for day, symbols in sorted(days.items())}


def plan_day(conn: sqlite3.Connection, day: str, symbols: Iterable[str], *, now: float) -> DayPlan:
    """What the repair would do to one session's live minutes. Reads only."""
    start, end = _day_bounds(day)
    plan = DayPlan(day)
    for symbol in symbols:
        rows = conn.execute(
            "SELECT ts, volume FROM bars_intraday WHERE symbol = ? AND timeframe = '1Min' AND ts >= ? AND ts < ? "
            "AND source = ?", (symbol, start, end, ARCHIVE_SOURCE_IBKR_L1),
        ).fetchall()
        if not rows:
            continue
        minutes = minute_counts(conn.execute(
            "SELECT ts, volume FROM l1_ticks WHERE symbol = ? AND ts >= ? AND ts < ? ORDER BY id",
            (symbol, start, end),
        ))
        for ts, stored in rows:
            ts, stored = float(ts), float(stored or 0.0)
            if ts > now - RECENT_SKIP_SEC:
                plan.kinds["recent"] += 1
                continue
            counts = minutes.get(ts)
            if counts is None:
                plan.kinds["no_ticks"] += 1
                continue
            kind, volume = classify(stored, counts)
            plan.kinds[kind] += 1
            if kind in ("fragment", "phantom") and round(volume) != round(stored):
                plan.changes.append(Change(symbol, ts, stored, volume))
    return plan


def apply(conn: sqlite3.Connection, changes: list[Change], *, batch: int = 500) -> int:
    """Write the changes, a short transaction per batch. A row changed since it was planned is left alone."""
    written = 0
    for i in range(0, len(changes), batch):
        with conn:
            for c in changes[i:i + batch]:
                cur = conn.execute(
                    "UPDATE bars_intraday SET volume = ? WHERE symbol = ? AND timeframe = '1Min' AND ts = ? "
                    "AND source = ? AND volume = ?",
                    (c.volume, c.symbol, c.ts, ARCHIVE_SOURCE_IBKR_L1, c.stored),
                )
                written += int(cur.rowcount or 0)
    return written


def report(plans: list[DayPlan], *, applied: int | None = None, top: int = 10) -> dict:
    """The tool's JSON report (``architecture/schema/market-data.md``, "The store's live minute keeps every share")."""
    totals: Counter = Counter()
    by_symbol: Counter = Counter()
    for plan in plans:
        totals.update(plan.kinds)
        for c in plan.changes:
            by_symbol[(c.symbol, plan.day)] += abs(c.volume - c.stored)

    def counts(source: Counter) -> dict:
        return {k: int(source.get(k, 0)) for k in KINDS}

    return {
        "schema_version": SCHEMA_VERSION,
        "days": [{"day": p.day, **counts(p.kinds), "shares_added": round(p.shares_added),
                  "shares_removed": round(p.shares_removed)} for p in plans],
        "totals": {**counts(totals), "shares_added": round(sum(p.shares_added for p in plans)),
                   "shares_removed": round(sum(p.shares_removed for p in plans))},
        "top": [{"symbol": s, "day": d, "shares_moved": round(v)} for (s, d), v in by_symbol.most_common(top)],
        "applied": applied,
    }
