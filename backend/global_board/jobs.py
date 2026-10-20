"""What the Global page reads, and when (ADR 060). Each read is a job: a store key, whether it uses IBKR's historical
budget or a market-data line, and the function that reads it. ``due`` lists the jobs due now, most urgent first.

Keys: ``fx:<CCY>`` (once per ET date), ``quotes`` (the index quotes), ``flow:<id>`` (a market's 1-minute bars: while
its session is open, then once more after it closes), ``index_daily:<id>`` (its index's daily bars, once after each
close -- the closed day's move and the 7 D / 30 D move), ``daily_flow:<id>`` (its future's or ETF's daily bars, for
7 D / 30 D only), ``refused:<instrument>`` (what IBKR refused, kept ``GLOBAL_REFUSED_RETRY_SEC``).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from constants_global_board import (
    GLOBAL_DAILY_DURATION,
    GLOBAL_FLOW_BAR,
    GLOBAL_FLOW_DURATION,
    GLOBAL_FLOW_TTL_SEC,
    GLOBAL_IDLE_FLOW_TTL_SEC,
    GLOBAL_IDLE_QUOTES_TTL_SEC,
    GLOBAL_MARKETS,
    GLOBAL_QUOTES_TTL_SEC,
    GLOBAL_REFUSED_RETRY_SEC,
    GLOBAL_US_TZ,
)
from global_board import contracts, flows, markets, reads
from global_board.state import Store

FINAL_READ_LAG_SEC = 120.0   # a session's last bars are in IBKR's history this long after its close
DAY = 86400.0


@dataclass(frozen=True)
class Job:
    key: str
    budget: str                       # "history" | "lines"
    run: Callable[[], object]


def et_date(now: float) -> str:
    return datetime.fromtimestamp(now, ZoneInfo(GLOBAL_US_TZ)).date().isoformat()


# -- refusals -----------------------------------------------------------------------------------------------------
def refused(st: Store, instrument_key: str, now: float) -> dict | None:
    got = st.get(f"refused:{instrument_key}", now)
    if got and now - float(got.get("at") or 0.0) < GLOBAL_REFUSED_RETRY_SEC:
        return got
    return None


def remember_refusal(st: Store, kind: str, spec: Mapping, error: str, now: float) -> None:
    st.put(f"refused:{contracts.key(kind, spec)}",
           {"instrument": spec.get("label") or spec["symbol"], "kind": kind, "error": error, "at": now}, now)


# -- the reads ----------------------------------------------------------------------------------------------------
def session_market(m: Mapping, basis: str | None) -> Mapping:
    """A future trades in the market's own session; a country ETF in the US one."""
    return markets.US_ETF if basis == "etf" else m


def flow_value(m: Mapping, kind: str, got: dict, now: float) -> dict:
    sm = session_market(m, kind)
    shown = markets.shown(sm, now)
    prev = markets.previous(sm, shown) if shown else None
    segs = shown[1] if shown else []
    classified = flows.classify(got["bars"], got["instrument"]["multiplier"] or 1.0)
    return {
        "basis": kind, "instrument": got["instrument"], "currency": got["instrument"]["currency"],
        "session_date": shown[0].isoformat() if shown else None,
        "from": segs[0][0] if segs else None, "to": segs[-1][1] if segs else None,
        "sums": flows.sums(classified, segs),
        "hours": flows.hours(classified, markets.sessions_since(sm, now - 2 * DAY, now)),
        "move": flows.move_from_bars(got["bars"], segs, prev[1] if prev else None),
        "read_at": now,
    }


def read_flow(st: Store, m: Mapping, now: float) -> dict:
    day = et_date(now)
    tries: list[tuple[str, Mapping]] = []
    if m["future"] and not refused(st, contracts.key("future", m["future"]), now):
        tries.append(("future", m["future"]))
    tries.append(("etf", contracts.etf_spec(m["etf"])))
    for i, (kind, spec) in enumerate(tries):
        if i and not reads.history_ok():
            from ibkr.historical_service import HistoricalShed

            raise HistoricalShed("the ETF waits for IBKR's historical budget")
        try:
            got = reads.bars(kind, spec, day, duration=GLOBAL_FLOW_DURATION, bar_size=GLOBAL_FLOW_BAR,
                             use_rth=kind == "etf")
        except reads.Refused as exc:
            remember_refusal(st, kind, spec, f"{exc}", now)
            continue
        return flow_value(m, kind, got, now)
    raise reads.Stated("IBKR refused every instrument of this market")


def read_quotes(st: Store, now: float) -> dict:
    """The index quotes of every market whose index IBKR has not refused; a quote IBKR refused (its code and words,
    or no such contract) is remembered so the next reads skip it."""
    asked = [m for m in GLOBAL_MARKETS if m["index"] and not refused(st, contracts.key("index", m["index"]), now)]
    got = reads.index_quotes(asked, et_date(now)) if asked else {}
    for m in asked:
        why = (got.get(m["id"]) or {}).get("error") or ""
        if why[:1].isdigit() or why.startswith("IBKR does not know"):
            remember_refusal(st, "index", m["index"], why, now)
    return got


def read_index_daily(st: Store, m: Mapping, now: float) -> dict:
    try:
        got = reads.bars("index", m["index"], et_date(now), duration=GLOBAL_DAILY_DURATION, bar_size="1 day",
                         use_rth=True)
    except reads.Refused as exc:
        remember_refusal(st, "index", m["index"], f"{exc}", now)
        raise
    return {"instrument": got["instrument"], "rows": reads.daily_rows(got), "read_at": now}


def read_daily_flow(st: Store, m: Mapping, now: float) -> dict:
    flow = st.get(f"flow:{m['id']}", now) or {}
    kind = "future" if flow.get("basis") == "future" else "etf"
    spec = m["future"] if kind == "future" else contracts.etf_spec(m["etf"])
    try:
        got = reads.bars(kind, spec, et_date(now), duration=GLOBAL_DAILY_DURATION, bar_size="1 day",
                         use_rth=kind == "etf")
    except reads.Refused as exc:
        remember_refusal(st, kind, spec, f"{exc}", now)
        raise
    return {"basis": kind, "instrument": got["instrument"], "currency": got["instrument"]["currency"],
            "rows": reads.daily_rows(got), "read_at": now}


# -- when -----------------------------------------------------------------------------------------------------------
def _age(st: Store, key: str, now: float) -> float:
    at = st.answered_at(key)
    return now - at if at is not None else float("inf")


def currencies(st: Store, now: float) -> list[str]:
    """The currencies of the futures the flows read (a market not read yet: its future's)."""
    out: list[str] = []
    for m in GLOBAL_MARKETS:
        flow = st.get(f"flow:{m['id']}", now)
        ccy = (flow or {}).get("currency") or (m["future"] or {}).get("currency") or "USD"
        if ccy != "USD" and ccy not in out:
            out.append(ccy)
    return out


def flow_due(st: Store, m: Mapping, now: float, wanted: bool) -> bool:
    key = f"flow:{m['id']}"
    value = st.get(key, now)
    if value is None:
        return True
    sm = session_market(m, value.get("basis"))
    shown = markets.shown(sm, now)
    if shown is None:
        return False
    if value.get("session_date") != shown[0].isoformat():
        return True
    if markets.state(sm, now) == "open":
        return _age(st, key, now) >= (GLOBAL_FLOW_TTL_SEC if wanted else GLOBAL_IDLE_FLOW_TTL_SEC)
    close = shown[1][-1][1]
    return now >= close + FINAL_READ_LAG_SEC and float(value.get("read_at") or 0.0) < close + FINAL_READ_LAG_SEC


def index_daily_due(st: Store, m: Mapping, now: float, wanted_period: str) -> bool:
    if not m["index"] or refused(st, contracts.key("index", m["index"]), now):
        return False
    value = st.get(f"index_daily:{m['id']}", now)
    shown = markets.shown(m, now)
    if shown is None:
        return False
    closed_after = now >= shown[1][-1][1] + FINAL_READ_LAG_SEC
    has_day = bool(value) and any(r.get("date") == shown[0].isoformat() for r in value.get("rows") or [])
    if value is None:
        return closed_after or wanted_period != "1D"
    if closed_after and not has_day:
        return float(value.get("read_at") or 0.0) < shown[1][-1][1] + FINAL_READ_LAG_SEC
    return wanted_period != "1D" and et_date(float(value.get("read_at") or 0.0)) != et_date(now)


def daily_flow_due(st: Store, m: Mapping, now: float) -> bool:
    """Once per ET date, and once more after the market's session closes when the last read was taken while it
    traded (the 7 D / 30 D views count completed sessions only)."""
    value = st.get(f"daily_flow:{m['id']}", now)
    if value is None:
        return True
    read_at = float(value.get("read_at") or 0.0)
    if et_date(read_at) != et_date(now):
        return True
    shown = markets.shown(session_market(m, value.get("basis")), now)
    if shown is None:
        return False
    close = shown[1][-1][1]
    return now >= close + FINAL_READ_LAG_SEC and read_at < close + FINAL_READ_LAG_SEC


def due(st: Store, now: float, *, wanted: bool, period: str) -> list[Job]:
    """The jobs due now, most urgent first: exchange rates, the index quotes, open markets' flows, a closed market's
    last read, the closed day's index bars, and -- for 7 D / 30 D only -- the daily bars."""
    out: list[Job] = []
    day = et_date(now)
    for ccy in currencies(st, now):
        key = f"fx:{ccy}"
        got = st.get(key, now)
        if (got is None or got.get("read_for") != day) and not refused(st, contracts.key("fx", contracts.fx_spec(ccy)), now):
            out.append(Job(key, "history", lambda c=ccy: _fx(st, c, now)))
    if _age(st, "quotes", now) >= (GLOBAL_QUOTES_TTL_SEC if wanted else GLOBAL_IDLE_QUOTES_TTL_SEC):
        out.append(Job("quotes", "lines", lambda: read_quotes(st, now)))
    by_state = sorted(GLOBAL_MARKETS, key=lambda m: markets.state(m, now) != "open")
    for m in by_state:
        if flow_due(st, m, now, wanted):
            out.append(Job(f"flow:{m['id']}", "history", lambda m=m: read_flow(st, m, now)))
    for m in GLOBAL_MARKETS:
        if index_daily_due(st, m, now, period if wanted else "1D"):
            out.append(Job(f"index_daily:{m['id']}", "history", lambda m=m: read_index_daily(st, m, now)))
    if wanted and period != "1D":
        for m in GLOBAL_MARKETS:
            if daily_flow_due(st, m, now):
                out.append(Job(f"daily_flow:{m['id']}", "history", lambda m=m: read_daily_flow(st, m, now)))
    return [job for job in out if not st.held(job.key, now)]


def _fx(st: Store, currency: str, now: float) -> dict:
    try:
        got = reads.fx_close(currency, et_date(now))
    except reads.Refused as exc:
        remember_refusal(st, "fx", contracts.fx_spec(currency), f"{exc}", now)
        raise
    return {**got, "read_for": et_date(now)}
