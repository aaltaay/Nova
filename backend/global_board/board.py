"""The Global page's wire (ADR 060; shape in architecture/schema/global-board.md), composed from memory only.

Every number is IBKR's or a sum of IBKR's -- except each market's ``size``, its exchanges' published market
capitalisation (monthly, with its month and source) -- and none is estimated. A market with no answer yet reads
``null`` with the reason (the read's own failure, IBKR's refusal, or "waiting").
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from constants_global_board import (
    GLOBAL_IDLE_QUOTES_TTL_SEC,
    GLOBAL_MARKET_SIZES,
    GLOBAL_MARKETS,
    GLOBAL_MIXED_MOVE_PCT,
    GLOBAL_MIXED_PRESSURE_PCT,
    GLOBAL_PERIOD_SESSIONS,
    GLOBAL_READ_MIN_FLOWS,
    GLOBAL_READ_NET_PCT,
    GLOBAL_READ_REGION_PCT,
    GLOBAL_REGIONS,
    GLOBAL_SCHEMA_VERSION,
    GLOBAL_SUN_HOURS,
    GLOBAL_HISTORY_HEADROOM,
)
from global_board import contracts, flows, jobs, markets
from global_board.state import Store

QUOTE_FRESH_SEC = 2 * GLOBAL_IDLE_QUOTES_TTL_SEC
HOUR = 3600.0
WAITING = "waiting for IBKR"
READ_RULE = (f"Money in when the world's pressure is +{GLOBAL_READ_NET_PCT:g}% or more of the money that traded, "
             f"money out at -{GLOBAL_READ_NET_PCT:g}% or less; otherwise rotation when one region is at "
             f"+{GLOBAL_READ_REGION_PCT:g}% or more and another at -{GLOBAL_READ_REGION_PCT:g}% or less, else "
             f"balanced. No read until {GLOBAL_READ_MIN_FLOWS} markets have a flow in dollars.")


def _r(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _rate(st: Store, currency: str | None, now: float) -> tuple[float | None, dict | None]:
    if not currency or currency == "USD":
        return 1.0, None
    got = st.get(f"fx:{currency}", now)
    if not got or not got.get("usd_per_unit"):
        return None, None
    return float(got["usd_per_unit"]), {"currency": currency, "usd_per_unit": got["usd_per_unit"],
                                        "date": got.get("date")}


def _empty_flow(error: str | None) -> dict:
    return {"basis": None, "instrument": None, "from": None, "to": None, "bars": None, "sessions": None,
            "up_usd": None, "down_usd": None, "flat_usd": None, "traded_usd": None, "pressure_usd": None,
            "pressure_pct": None, "last_bar_at": None, "fx": None, "at": None, "error": error, "refused": []}


def _money(sums: Mapping, rate: float | None) -> dict:
    up, down, flat, traded = (sums.get(k, 0.0) for k in ("up", "down", "flat", "traded"))
    return {"up_usd": flows.usd(up, rate), "down_usd": flows.usd(down, rate), "flat_usd": flows.usd(flat, rate),
            "traded_usd": flows.usd(traded, rate), "pressure_usd": flows.usd(up - down, rate),
            "pressure_pct": flows.pressure_pct(up, down, traded)}


def _why(st: Store, key: str) -> str:
    failed = st.failure(key)
    return failed[0] if failed else WAITING


def _flow_1d(st: Store, m: Mapping, now: float) -> dict:
    value = st.get(f"flow:{m['id']}", now)
    if value is None:
        return _empty_flow(_why(st, f"flow:{m['id']}"))
    rate, fx = _rate(st, value.get("currency"), now)
    sums = value.get("sums") or {}
    return {**_empty_flow(None), "basis": value.get("basis"), "instrument": value.get("instrument"),
            "from": value.get("from"), "to": value.get("to"), "bars": sums.get("bars"),
            **_money(sums, rate), "last_bar_at": sums.get("last_bar_at"), "fx": fx, "at": value.get("read_at"),
            "error": None if rate else f"no {value.get('currency')} rate from IBKR yet"}


def completed(rows: Sequence[Mapping], sm: Mapping, now: float) -> list[Mapping]:
    """Daily rows of sessions that have closed on the market's clock: a forming day (today's session still
    trading, or a future's day that began before the cash open) is left out until its session ends."""
    shown = markets.shown(sm, now)
    if shown is None:
        return list(rows)
    if now >= shown[1][-1][1]:
        last = shown[0].isoformat()
    else:
        prev = markets.previous(sm, shown)
        last = prev[0].isoformat() if prev else ""
    return [r for r in rows if (r.get("date") or "") <= last]


def _flow_days(st: Store, m: Mapping, period: str, now: float) -> dict:
    value = st.get(f"daily_flow:{m['id']}", now)
    if value is None:
        return _empty_flow(_why(st, f"daily_flow:{m['id']}"))
    index_rows = completed((st.get(f"index_daily:{m['id']}", now) or {}).get("rows") or [], m, now)
    rows = completed(value.get("rows") or [], jobs.session_market(m, value.get("basis")), now)
    sign_rows = index_rows or rows
    mult = (value.get("instrument") or {}).get("multiplier") or 1.0
    sums = flows.daily_sums(rows, sign_rows, GLOBAL_PERIOD_SESSIONS[period], mult)
    rate, fx = _rate(st, value.get("currency"), now)
    return {**_empty_flow(None), "basis": value.get("basis"), "instrument": value.get("instrument"),
            "from": sums["from"], "to": sums["to"], "sessions": sums["sessions"], **_money(sums, rate),
            "fx": fx, "at": value.get("read_at"),
            "error": None if rate else f"no {value.get('currency')} rate from IBKR yet"}


def _move(basis: str | None, instrument: dict | None, got: Mapping | None, at: float | None,
          data_type: str | None = None, error: str | None = None) -> dict:
    got = got or {}
    return {"basis": basis if got.get("pct") is not None else None, "instrument": instrument,
            "pct": got.get("pct"), "last": got.get("last"), "prev_close": got.get("prev_close"), "at": at,
            "data_type": data_type, "error": None if got.get("pct") is not None else error}


def _closed_day_move(rows: Sequence[Mapping], day: str | None) -> dict | None:
    closes = [r for r in rows if r.get("close")]
    for i, row in enumerate(closes):
        if row.get("date") == day and i:
            prior = closes[i - 1]["close"]
            return {"pct": round((row["close"] / prior - 1.0) * 100.0, 3), "last": row["close"], "prev_close": prior}
    return None


def _move_1d(st: Store, m: Mapping, session: Mapping, quotes: Mapping, quotes_at: float | None,
             now: float) -> dict:
    flow = st.get(f"flow:{m['id']}", now) or {}
    index = contracts.instrument("index", m["index"]) if m["index"] else None
    quote = quotes.get(m["id"]) or {}
    open_now = session["state"] in ("open", "break")
    if index and open_now and quote.get("pct") is not None and quotes_at and now - quotes_at <= QUOTE_FRESH_SEC:
        return _move("index", index, quote, quote.get("at"), quote.get("data_type"))
    if index and not open_now:
        daily = st.get(f"index_daily:{m['id']}", now) or {}
        got = _closed_day_move(daily.get("rows") or [], session.get("date"))
        if got:
            return _move("index", index, got, daily.get("read_at"))
    if flow.get("move"):
        return _move(flow.get("basis"), flow.get("instrument"), flow["move"], flow.get("read_at"))
    return _move(None, index, None, None, error=quote.get("error") or _why(st, f"flow:{m['id']}"))


def _move_days(st: Store, m: Mapping, period: str, now: float) -> dict:
    n = GLOBAL_PERIOD_SESSIONS[period]
    daily = st.get(f"index_daily:{m['id']}", now) or {}
    got = flows.daily_move(completed(daily.get("rows") or [], m, now), n)
    if got:
        return _move("index", daily.get("instrument"), got, daily.get("read_at"))
    other = st.get(f"daily_flow:{m['id']}", now) or {}
    got = flows.daily_move(completed(other.get("rows") or [], jobs.session_market(m, other.get("basis")), now), n)
    if got:
        return _move(other.get("basis"), other.get("instrument"), got, other.get("read_at"))
    return _move(None, None, None, None, error=_why(st, f"daily_flow:{m['id']}"))


def _refused(st: Store, m: Mapping, now: float) -> list[dict]:
    out = []
    for kind, spec in (("future", m["future"]), ("index", m["index"]), ("etf", contracts.etf_spec(m["etf"]))):
        got = jobs.refused(st, contracts.key(kind, spec), now) if spec else None
        if got:
            out.append({"instrument": got.get("instrument"), "error": got.get("error")})
    return out


def _mixed(flow: Mapping, move: Mapping) -> bool:
    p, mv = flow.get("pressure_pct"), move.get("pct")
    if p is None or mv is None:
        return False
    return abs(p) >= GLOBAL_MIXED_PRESSURE_PCT and abs(mv) >= GLOBAL_MIXED_MOVE_PCT and (p > 0) != (mv > 0)


def market_row(st: Store, m: Mapping, now: float, period: str, quotes: Mapping, quotes_at: float | None) -> dict:
    session = markets.session_view(m, now)
    if period == "1D":
        flow, move = _flow_1d(st, m, now), _move_1d(st, m, session, quotes, quotes_at, now)
    else:
        flow, move = _flow_days(st, m, period, now), _move_days(st, m, period, now)
    flow["refused"] = _refused(st, m, now)
    return {"id": m["id"], "name": m["name"], "exchange": m["exchange"], "city": m["city"], "region": m["region"],
            "lat": m["lat"], "lon": m["lon"], "tz": m["tz"], "session": session, "move": move, "flow": flow,
            "mixed": _mixed(flow, move), "size": size(m["id"])}


def size(market_id: str) -> dict | None:
    """The market's published size (``GLOBAL_MARKET_SIZES``): its exchanges' domestic market capitalisation, with
    the month and source it comes from -- the page's one number that is not IBKR's, and not live."""
    got = GLOBAL_MARKET_SIZES.get(market_id)
    if got is None:
        return None
    parts = [{"name": p["name"], "usd": p["usd"]} for p in got["parts"]]
    return {"usd": sum(p["usd"] for p in parts), "parts": parts, "as_of": got["as_of"], "source": got["source"],
            "url": got["url"]}


def totals(rows: Sequence[Mapping]) -> dict:
    with_usd = [r for r in rows if r["flow"].get("pressure_usd") is not None]
    up = sum(r["flow"]["up_usd"] or 0.0 for r in with_usd)
    down = sum(r["flow"]["down_usd"] or 0.0 for r in with_usd)
    traded = sum(r["flow"]["traded_usd"] or 0.0 for r in with_usd)
    moves = [r["move"]["pct"] for r in rows if r["move"].get("pct") is not None]
    return {"pressure_usd": _r(up - down) if with_usd else None, "traded_usd": _r(traded) if with_usd else None,
            "pressure_pct": flows.pressure_pct(up, down, traded), "markets": len(rows), "flows": len(with_usd),
            "up": sum(1 for v in moves if v > 0), "down": sum(1 for v in moves if v < 0),
            "avg_move_pct": _r(sum(moves) / len(moves), 3) if moves else None}


def read(world: Mapping, regions: Sequence[Mapping]) -> dict:
    if world["flows"] < GLOBAL_READ_MIN_FLOWS or world["pressure_pct"] is None:
        return {"verdict": None, "headline": "Not enough markets read yet",
                "detail": f"{world['flows']} of {world['markets']} markets have a flow in dollars", "rule": READ_RULE}
    known = [r for r in regions if r["flows"] and r["pressure_pct"] is not None]
    pct = world["pressure_pct"]
    if pct >= GLOBAL_READ_NET_PCT:
        verdict, headline = "money_in", "Money coming in"
    elif pct <= -GLOBAL_READ_NET_PCT:
        verdict, headline = "money_out", "Money going out"
    elif (any(r["pressure_pct"] >= GLOBAL_READ_REGION_PCT for r in known)
          and any(r["pressure_pct"] <= -GLOBAL_READ_REGION_PCT for r in known)):
        verdict, headline = "rotation", "Rotation, not an exit"
    else:
        verdict, headline = "quiet", "Balanced"
    best = max(known, key=lambda r: r["pressure_usd"] or 0.0, default=None)
    worst = min(known, key=lambda r: r["pressure_usd"] or 0.0, default=None)
    if best and worst and (worst["pressure_usd"] or 0) < 0 < (best["pressure_usd"] or 0):
        detail = f"{worst['label']} sold, {best['label']} bought"
    elif best and (best["pressure_usd"] or 0) > 0:
        detail = f"{best['label']} led the buying"
    elif worst and (worst["pressure_usd"] or 0) < 0:
        detail = f"{worst['label']} led the selling"
    else:
        detail = "no region leaned either way"
    return {"verdict": verdict, "headline": headline, "detail": detail, "rule": READ_RULE}


def sun(st: Store, now: float) -> dict:
    end = now - now % HOUR + HOUR
    start = end - GLOBAL_SUN_HOURS * HOUR
    hours = [{"t": start + i * HOUR, "net_usd": 0.0, "traded_usd": 0.0, "markets": 0, "by_region": {}}
             for i in range(GLOBAL_SUN_HOURS)]
    for m in GLOBAL_MARKETS:
        flow = st.get(f"flow:{m['id']}", now) or {}
        rate, _fx = _rate(st, flow.get("currency"), now)
        if rate is None:
            continue
        for t, net, traded in flow.get("hours") or []:
            if not start <= t < end:
                continue
            row = hours[int((t - start) // HOUR)]
            row["net_usd"] += net * rate
            row["traded_usd"] += traded * rate
            row["markets"] += 1
            row["by_region"][m["region"]] = row["by_region"].get(m["region"], 0.0) + net * rate
    for row in hours:
        row["net_usd"], row["traded_usd"] = round(row["net_usd"], 2), round(row["traded_usd"], 2)
        row["by_region"] = {k: round(v, 2) for k, v in row["by_region"].items()}
    sessions = [{"market": m["id"], "region": m["region"], "start": max(a, start), "end": min(b, end)}
                for m in GLOBAL_MARKETS for a, b in markets.sessions_since(m, start, end) if b > start and a < end]
    return {"from": start, "to": end, "now": now, "hours": hours, "sessions": sessions}


def compose(st: Store, now: float, *, enabled: bool, replay_desk: bool, period: str,
            history_left: int | None = None, history_headroom: int = GLOBAL_HISTORY_HEADROOM) -> dict:
    quotes = st.get("quotes", now) or {}
    rows = [market_row(st, m, now, period, quotes, st.answered_at("quotes")) for m in GLOBAL_MARKETS]
    regions = [{"id": rid, "label": label, **totals([r for r in rows if r["region"] == rid])}
               for rid, label in GLOBAL_REGIONS.items()]
    world = totals(rows)
    ok, at, error = st.source_view()
    missing = any(st.answered_at(f"flow:{m['id']}") is None and st.failure(f"flow:{m['id']}") is None
                  for m in GLOBAL_MARKETS)
    return {
        "schema_version": GLOBAL_SCHEMA_VERSION, "generated_at": now, "enabled": enabled,
        "loading": bool(enabled and ok is not False and missing), "replay_desk": replay_desk, "period": period,
        "read": read(world, regions), "world": world, "regions": regions, "markets": rows, "sun": sun(st, now),
        "sources": [{"id": "ibkr", "label": "IBKR", "ok": ok, "at": at, "error": error}],
        "budget": {"history_left": history_left, "history_headroom": history_headroom,
                   "waiting": st.waiting_for()},
    }
