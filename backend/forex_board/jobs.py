"""What the Forex page reads, and when (ADR 062). Each read is a job: a store key, whether it uses IBKR's historical
budget or a market-data line, and the function that reads it. ``due`` lists the jobs due now, most urgent first.

Keys: ``quotes`` (every pair's spot quote, while the FX day is open), ``hourly:<CODE>`` (a pair's one-hour midpoints:
once per completed hour of the FX day, once more after it ends), ``flow:<CODE>`` (a future's one-minute trades, kept
as the FX day's sums: while the day is open, then once more after it closes), ``daily:<CODE>`` and
``flow_daily:<CODE>`` (daily bars: once per FX day, only while the page is open), ``refused:<instrument>`` (what IBKR
refused, kept ``FOREX_REFUSED_RETRY_SEC``). Each answer keeps only what the board needs.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from constants_forex_board import (
    FOREX_CURRENCIES,
    FOREX_DAILY_DURATION,
    FOREX_DAILY_KEEP,
    FOREX_FINAL_READ_LAG_SEC,
    FOREX_FLOW_BAR,
    FOREX_FLOW_DURATION,
    FOREX_FLOW_TTL_SEC,
    FOREX_HOURLY_BAR,
    FOREX_HOURLY_DURATION,
    FOREX_IDLE_FLOW_TTL_SEC,
    FOREX_IDLE_QUOTES_TTL_SEC,
    FOREX_QUOTES_TTL_SEC,
    FOREX_REFUSED_RETRY_SEC,
)
from forex_board import clock, contracts, money, prices, reads
from forex_board.state import Store

HOUR = 3600.0
LAG = FOREX_FINAL_READ_LAG_SEC


@dataclass(frozen=True)
class Job:
    key: str
    budget: str                       # "history" | "lines"
    run: Callable[[], object]


def et_date(now: float) -> str:
    return datetime.fromtimestamp(now, clock.ET).date().isoformat()


# -- refusals -----------------------------------------------------------------------------------------------------
def refused(st: Store, instrument_key: str, now: float) -> dict | None:
    got = st.get(f"refused:{instrument_key}", now)
    if got and now - float(got.get("at") or 0.0) < FOREX_REFUSED_RETRY_SEC:
        return got
    return None


def remember_refusal(st: Store, kind: str, spec: Mapping, error: str, now: float) -> None:
    st.put(f"refused:{contracts.key(kind, spec)}",
           {"instrument": spec.get("label") or spec["symbol"], "kind": kind, "error": error, "at": now}, now)


def spot_ok(st: Store, cur: Mapping, now: float) -> bool:
    spec = contracts.spot_spec(cur)
    return spec is not None and not refused(st, contracts.key("spot", spec), now)


def future_ok(st: Store, cur: Mapping, now: float) -> bool:
    spec = contracts.future_spec(cur)
    return spec is not None and not refused(st, contracts.key("future", spec), now)


# -- the reads ----------------------------------------------------------------------------------------------------
def read_quotes(st: Store, now: float) -> dict:
    """Every pair IBKR has not refused, from a line held for a moment; a pair IBKR refuses (its code and words, or no
    such contract) is remembered so the next reads skip it."""
    asked = [c for c in FOREX_CURRENCIES if spot_ok(st, c, now)]
    got = reads.spot_quotes(asked, et_date(now)) if asked else {}
    for cur in asked:
        why = (got.get(cur["code"]) or {}).get("error") or ""
        if why[:1].isdigit() or why.startswith("IBKR does not know"):
            remember_refusal(st, "spot", contracts.spot_spec(cur), why, now)
    return got


def _bars(st: Store, kind: str, spec: Mapping, now: float, **kw) -> dict:
    try:
        return reads.bars(kind, spec, et_date(now), **kw)
    except reads.Refused as exc:
        remember_refusal(st, kind, spec, f"{exc}", now)
        raise


def read_hourly(st: Store, cur: Mapping, now: float) -> dict:
    fx = clock.day(now)
    got = _bars(st, "spot", contracts.spot_spec(cur), now, duration=FOREX_HOURLY_DURATION, bar_size=FOREX_HOURLY_BAR,
                what="MIDPOINT")
    return {"fx_from": fx["from"], "fx_date": fx["date"], "day": prices.day_from_bars(got["bars"], fx["from"], fx["to"]),
            "instrument": got["instrument"], "read_at": now}


def read_daily(st: Store, cur: Mapping, now: float) -> dict:
    fx = clock.day(now)
    got = _bars(st, "spot", contracts.spot_spec(cur), now, duration=FOREX_DAILY_DURATION, bar_size="1 day",
                what="MIDPOINT")
    return {"fx_date": fx["date"], "rows": reads.daily_rows(got)[-FOREX_DAILY_KEEP:], "instrument": got["instrument"],
            "read_at": now}


def read_flow(st: Store, cur: Mapping, now: float) -> dict:
    fx = clock.day(now)
    spec = contracts.future_spec(cur)
    got = _bars(st, "future", spec, now, duration=FOREX_FLOW_DURATION, bar_size=FOREX_FLOW_BAR, what="TRADES")
    inst = got["instrument"]
    classified = money.classify(got["bars"], inst["multiplier"] or float(spec["multiplier"]), spec["inverted"])
    return {"fx_from": fx["from"], "fx_date": fx["date"], "sums": money.sums(classified, fx["from"], fx["to"]),
            "hours": [[h, net, traded] for h, (net, traded) in sorted(money.hours(classified, fx["from"]).items())],
            "levels": money.levels(got["bars"], fx["from"], fx["to"]), "instrument": inst,
            "inverted": spec["inverted"], "read_at": now}


def read_flow_daily(st: Store, cur: Mapping, now: float) -> dict:
    fx = clock.day(now)
    spec = contracts.future_spec(cur)
    got = _bars(st, "future", spec, now, duration=FOREX_DAILY_DURATION, bar_size="1 day", what="TRADES")
    return {"fx_date": fx["date"], "rows": reads.daily_rows(got)[-FOREX_DAILY_KEEP:], "instrument": got["instrument"],
            "inverted": spec["inverted"], "read_at": now}


# -- when -----------------------------------------------------------------------------------------------------------
def _age(st: Store, key: str, now: float) -> float:
    at = st.answered_at(key)
    return now - at if at is not None else float("inf")


def hourly_due(value: Mapping | None, fx: Mapping, now: float) -> bool:
    """A new FX day; then once per completed hour, two minutes after it ends (the last after the day's end)."""
    if value is None or value.get("fx_from") != fx["from"]:
        return True
    last_end = fx["from"] + math.floor(clock.hours_done(fx, now)) * HOUR
    if last_end <= fx["from"]:
        return False
    return now >= last_end + LAG and float(value.get("read_at") or 0.0) < last_end + LAG


def flow_due(value: Mapping | None, fx: Mapping, now: float, wanted: bool) -> bool:
    if value is None or value.get("fx_from") != fx["from"]:
        return True
    read_at = float(value.get("read_at") or 0.0)
    if fx["open"]:
        return now - read_at >= (FOREX_FLOW_TTL_SEC if wanted else FOREX_IDLE_FLOW_TTL_SEC)
    return now >= fx["to"] + LAG and read_at < fx["to"] + LAG


def daily_due(value: Mapping | None, fx: Mapping, now: float) -> bool:
    """Once per FX day, two minutes after it starts (the day before is then complete in IBKR's daily bars)."""
    if value is not None and value.get("fx_date") == fx["date"]:
        return False
    return value is None or now >= fx["from"] + LAG


def due(st: Store, now: float, *, wanted: bool, period: str) -> list[Job]:
    """The jobs due now, most urgent first: the quotes, each pair's newest hour, each future's flow, and -- while the
    page is open -- the daily bars (7 D / 30 D, and a normal day's range and volume)."""
    fx = clock.day(now)
    out: list[Job] = []
    spot = [c for c in FOREX_CURRENCIES if spot_ok(st, c, now)]
    futures = [c for c in FOREX_CURRENCIES if future_ok(st, c, now)]
    if fx["open"] and spot and _age(st, "quotes", now) >= (FOREX_QUOTES_TTL_SEC if wanted else FOREX_IDLE_QUOTES_TTL_SEC):
        out.append(Job("quotes", "lines", lambda: read_quotes(st, now)))
    for cur in spot:
        if hourly_due(st.get(f"hourly:{cur['code']}", now), fx, now):
            out.append(Job(f"hourly:{cur['code']}", "history", lambda c=cur: read_hourly(st, c, now)))
    for cur in futures:
        if flow_due(st.get(f"flow:{cur['code']}", now), fx, now, wanted):
            out.append(Job(f"flow:{cur['code']}", "history", lambda c=cur: read_flow(st, c, now)))
    if wanted:
        for cur in spot:
            if daily_due(st.get(f"daily:{cur['code']}", now), fx, now):
                out.append(Job(f"daily:{cur['code']}", "history", lambda c=cur: read_daily(st, c, now)))
        for cur in futures:
            if daily_due(st.get(f"flow_daily:{cur['code']}", now), fx, now):
                out.append(Job(f"flow_daily:{cur['code']}", "history", lambda c=cur: read_flow_daily(st, c, now)))
    return [job for job in out if not st.held(job.key, now)]
