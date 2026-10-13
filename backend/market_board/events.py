"""The day's scheduled events (ADR 053): economic releases, FOMC decisions, the biggest names' earnings, closures.

Sources, each named on the page: BEA's release-dates JSON (fetched), BLS's 2026 schedule and the Fed's FOMC
decisions and SIFMA's bond-market days (constants copied from the published calendars -- BLS blocks scripts),
NYSE holidays and early closes (``constants_nova_os``), and earnings from Nova's Finnhub calendar for the biggest
names only. Pure functions over those inputs; ``fetch_bea`` is the one network read.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from constants_market_board import (
    MARKET_BEA_RELEASES,
    MARKET_BEA_URL,
    MARKET_BLS_RELEASES,
    MARKET_BOND_CLOSED,
    MARKET_BOND_EARLY_CLOSE,
    MARKET_BOND_EARLY_CLOSE_ET,
    MARKET_EVENTS_DAYS_AHEAD,
    MARKET_EVENTS_MAX,
    MARKET_FOMC_DECISIONS,
    MARKET_FOMC_TIME_ET,
    MARKET_HTTP_TIMEOUT_SEC,
    MARKET_HTTP_USER_AGENT,
)
from constants_nova_os import NOVA_OS_NYSE_EARLY_CLOSE_NAMES, NOVA_OS_NYSE_HOLIDAY_NAMES
from market_board.clock import ET, at
from market_board.state import Stated

BEA_SOURCE = "bea"
_EARNINGS_TIME = {"bmo": (8 * 60, "before the open"), "amc": (16 * 60 + 5, "after the close")}


class CalendarError(Stated):
    """A calendar could not be fetched or read; the page states it."""


def _et_stamp(text: str) -> float:
    """"2026-10-14T08:30" (ET) -> epoch seconds."""
    return datetime.fromisoformat(text).replace(tzinfo=ET).timestamp()


def fetch_bea() -> dict[str, list[str]]:
    """``{release name: [ISO timestamps]}`` for the releases the page shows."""
    import requests

    try:
        resp = requests.get(MARKET_BEA_URL, timeout=MARKET_HTTP_TIMEOUT_SEC,
                            headers={"User-Agent": MARKET_HTTP_USER_AGENT})
    except requests.RequestException as exc:
        raise CalendarError(type(exc).__name__) from exc
    if resp.status_code != 200:
        raise CalendarError(f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise CalendarError("not JSON") from exc
    out: dict[str, list[str]] = {}
    for name in MARKET_BEA_RELEASES:
        entry = data.get(name) if isinstance(data, dict) else None
        dates = entry.get("release_dates") if isinstance(entry, dict) else None
        out[name] = sorted({str(d) for d in dates or []})
    return out


def _window(today: date) -> tuple[float, float]:
    return at(today, 0), at(today + timedelta(days=MARKET_EVENTS_DAYS_AHEAD + 1), 0)


def upcoming(today: date, *, bea: dict[str, list[str]] | None, earnings: list[dict] | None,
           biggest: set[str]) -> list[dict[str, Any]]:
    """Today's and the next days' events, soonest first, at most ``MARKET_EVENTS_MAX``."""
    lo, hi = _window(today)
    items: list[dict[str, Any]] = []

    def add(when: float, kind: str, title: str, detail: str | None, source: str) -> None:
        if lo <= when < hi:
            items.append({"at": when, "kind": kind, "title": title, "detail": detail, "source": source})

    for stamp, title, detail in MARKET_BLS_RELEASES:
        add(_et_stamp(stamp), "econ", title, detail, "bls")
    for name, stamps in (bea or {}).items():
        for stamp in stamps:
            try:
                when = datetime.fromisoformat(stamp).timestamp()
            except ValueError:
                continue
            add(when, "econ", MARKET_BEA_RELEASES.get(name, name), name, BEA_SOURCE)
    for day in MARKET_FOMC_DECISIONS:
        add(_et_stamp(f"{day}T{MARKET_FOMC_TIME_ET}"), "fomc", "FOMC decision", "Fed statement and rate", "fed")
    for row in earnings or []:
        sym = str(row.get("symbol") or "").upper()
        if sym not in biggest or not row.get("date"):
            continue
        minutes, when_words = _EARNINGS_TIME.get(str(row.get("hour") or "").lower(), (12 * 60, "during the day"))
        try:
            day = date.fromisoformat(str(row["date"]))
        except ValueError:
            continue
        add(at(day, minutes), "earnings", f"{sym} earnings", when_words, "finnhub")
    for offset in range(MARKET_EVENTS_DAYS_AHEAD + 1):
        d = today + timedelta(days=offset)
        iso = d.isoformat()
        if iso in NOVA_OS_NYSE_HOLIDAY_NAMES and d.weekday() < 5:
            add(at(d, 9 * 60 + 30), "holiday", "US stocks closed", NOVA_OS_NYSE_HOLIDAY_NAMES[iso], "nyse")
        if iso in NOVA_OS_NYSE_EARLY_CLOSE_NAMES:
            add(at(d, 13 * 60), "holiday", "US stocks close at 13:00", NOVA_OS_NYSE_EARLY_CLOSE_NAMES[iso], "nyse")
        if iso in MARKET_BOND_CLOSED:
            add(at(d, 8 * 60), "holiday", "Bond market closed", MARKET_BOND_CLOSED[iso], "sifma")
    items.sort(key=lambda e: (e["at"], e["kind"], e["title"]))
    return items[:MARKET_EVENTS_MAX]


def bond_market(day: date) -> dict[str, Any]:
    iso = day.isoformat()
    if iso in MARKET_BOND_CLOSED:
        return {"closed": True, "early_close_at": None, "why": MARKET_BOND_CLOSED[iso]}
    if iso in MARKET_BOND_EARLY_CLOSE:
        hh, mm = (int(x) for x in MARKET_BOND_EARLY_CLOSE_ET.split(":"))
        return {"closed": False, "early_close_at": at(day, hh * 60 + mm), "why": MARKET_BOND_EARLY_CLOSE[iso]}
    return {"closed": False, "early_close_at": None, "why": None}
