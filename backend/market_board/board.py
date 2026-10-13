"""The Market page's wire (ADR 053; shape in architecture/schema/market-board.md), composed from the store.

Nothing here asks IBKR or the network: every number is what a refresher last answered, ``None`` when it has not
(or its answer is too old), with the reason where one is known.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from constants_market_board import (
    MARKET_BARS_FRESH_SEC,
    MARKET_BARS_QUOTES_TTL_SEC,
    MARKET_BIGGEST_PER_SECTOR,
    MARKET_CLOSES_RETRY_SEC,
    MARKET_ETF_TTL_SEC,
    MARKET_HOLDINGS_TTL_SEC,
    MARKET_LINE_START_MIN_ET,
    MARKET_LINES_TTL_SEC,
    MARKET_MOVERS_TTL_SEC,
    MARKET_PERIOD_SESSIONS,
    MARKET_PERIODS,
    MARKET_QUOTES,
    MARKET_QUOTES_TTL_SEC,
    MARKET_SCHEMA_VERSION,
    MARKET_SECTORS,
    MARKET_SPREAD_LEGS,
    MARKET_TNX_TENTHS_ABOVE,
)
from constants_scanner import SESSION_RTH_OPEN_MIN_ET
from market_board import breadth, climate, clock, day_read, events, holdings, sectors
from market_board.state import Store

_FIRST_READS = ("climate",)


def _pct(a: float | None, b: float | None) -> float | None:
    return round(100.0 * (a / b - 1.0), 2) if a is not None and b else None


def _tile(spec: dict, q: dict | None, line: list | None, day: date, now: float) -> dict[str, Any]:
    q = q or {}
    last, prev = q.get("last"), q.get("prev_close")
    scale = 10.0 if spec["id"] == "tnx" and (last or prev or 0) >= MARKET_TNX_TENTHS_ABOVE else 1.0
    last = last / scale if last is not None else None
    prev = prev / scale if prev is not None else None
    start = clock.at(day, MARKET_LINE_START_MIN_ET)
    points = [[t, v / scale] for t, v in (line or []) if t >= start and v is not None]
    if last is not None and points and now > points[-1][0]:
        points.append([now, last])
    return {
        "id": spec["id"], "label": spec["label"], "symbol": spec["symbol"],
        "kind": {"CONTFUT": "future", "IND": "index", "CRYPTO": "crypto"}.get(spec["sec_type"], "spread"),
        "exchange": spec["exchange"], "contract": q.get("contract"), "last": last, "prev_close": prev,
        "change": round(last - prev, 4) if last is not None and prev is not None else None,
        "change_pct": _pct(last, prev), "price_basis": q.get("price_basis"), "data_type": q.get("data_type"),
        "at": q.get("at"), "line": points, "error": q.get("error"),
    }


def _from_bars(q: dict | None, line: list | None, prior: dict | None, now: float) -> dict | None:
    """A tile's quote from its bars when IBKR gave no snapshot: the last 5-minute close, the prior daily close."""
    if q and q.get("last") is not None:
        if q.get("prev_close") is None and prior:
            return {**q, "prev_close": prior.get("close")}   # a snapshot with a print but no close
        return q
    if not line or now - line[-1][0] > MARKET_BARS_FRESH_SEC:
        return q
    return {**(q or {}), "last": line[-1][1], "price_basis": "bars", "data_type": "bars", "at": line[-1][0],
            "prev_close": (q or {}).get("prev_close") or (prior or {}).get("close"), "error": None}


def _spread(tiles: dict[str, dict], spec: dict) -> dict[str, Any]:
    a, b = (tiles.get(x) or {} for x in MARKET_SPREAD_LEGS)
    pct = round(a["change_pct"] - b["change_pct"], 2) if a.get("change_pct") is not None and \
        b.get("change_pct") is not None else None
    line = []
    if a.get("prev_close") and b.get("prev_close"):
        b_by_t = {int(t // 300): v for t, v in b.get("line") or []}
        for t, v in a.get("line") or []:
            bv = b_by_t.get(int(t // 300))
            if bv is not None:
                line.append([t, round(100.0 * (v / a["prev_close"] - bv / b["prev_close"]), 3)])
    return {"id": spec["id"], "label": spec["label"], "symbol": spec["symbol"], "kind": "spread", "exchange": "",
            "contract": None, "last": None, "prev_close": None, "change": None, "change_pct": pct,
            "price_basis": None, "data_type": a.get("data_type"), "at": a.get("at"), "line": line,
            "error": None if pct is not None else (a.get("error") or b.get("error"))}


def _holdings(st: Store, now: float):
    def get(etf: str) -> dict | None:
        return st.get(f"holdings:{etf}", now, MARKET_HOLDINGS_TTL_SEC) or holdings.cached(etf)
    return get


def compose(st: Store, now: float, *, enabled: bool, replay_desk: bool, params: dict[str, str]) -> dict[str, Any]:
    day = clock.trading_date(now)
    today = day.isoformat()
    sess = clock.session(now)
    quotes = st.get("quotes", now, MARKET_QUOTES_TTL_SEC) or {}
    tiles: dict[str, dict] = {}
    for spec in MARKET_QUOTES:
        if spec["sec_type"] == "SPREAD":
            continue
        line = st.get(f"line:{spec['id']}", now, MARKET_LINES_TTL_SEC)
        q = _from_bars(quotes.get(spec["id"]), line, st.get(f"prior:{spec['id']}", now, 86400.0 * 4), now)
        tiles[spec["id"]] = _tile(spec, q, line, day, now)
        if spec["id"] not in quotes and st.error("quotes"):
            tiles[spec["id"]]["error"] = st.error("quotes")
    for spec in MARKET_QUOTES:
        if spec["sec_type"] == "SPREAD":
            tiles[spec["id"]] = _spread(tiles, spec)
    open_at = clock.at(day, SESSION_RTH_OPEN_MIN_ET)
    breadth_block = breadth.compose(now, day, sess["phase"], st.get("breadth_latest", now, 180.0),
                                    st.error("breadth"))
    movers = st.get("movers", now, MARKET_MOVERS_TTL_SEC) or st.get("movers_bars", now, MARKET_BARS_QUOTES_TTL_SEC)
    ctx = {
        "today": today,
        "etf_quotes": (st.get("etf_quotes", now, MARKET_ETF_TTL_SEC)
                       or st.get("etf_bars", now, MARKET_BARS_QUOTES_TTL_SEC) or {}),
        "closes": lambda s: st.get(f"closes:{s}", now, MARKET_CLOSES_RETRY_SEC * 96),
        "holdings": _holdings(st, now),
        "movers": (movers or {}).get("quotes") or {},
        "movers_read": movers is not None,
        "pool_quotes": st.get("pool_quotes", now, MARKET_ETF_TTL_SEC * 3) or {},
        "period_from": {p: clock.sessions_back(day, MARKET_PERIOD_SESSIONS[p])[0].isoformat() for p in MARKET_PERIODS},
    }
    climate_ready = st.get("climate", now, 600.0) is not None
    clim = climate.compose(params["climate"], now) if climate_ready else None
    today_clim = climate.today_numbers(now) if climate_ready else {}
    checks = [
        day_read.futures(tiles),
        day_read.breadth(breadth_block, open_at),
        day_read.vix(tiles.get("vix")),
        day_read.small_caps(tiles["small_caps"]["change_pct"]),
        day_read.runners(today_clim.get("runners"), today_clim.get("runners_avg")),
        day_read.gappers(today_clim.get("gappers_held") or 0, today_clim.get("gappers_total") or 0,
                         now >= open_at, open_at),
    ]
    biggest = {s for _, etf in MARKET_SECTORS for s in sectors.members(etf, ctx["holdings"])[:MARKET_BIGGEST_PER_SECTOR]}
    runners = climate.runners_by_theme(params["top_period"], now) if climate_ready else None
    since = st.wanted_since()
    loading = enabled and not all(st.tried_since(k, since) for k in _FIRST_READS)
    return {
        "schema_version": MARKET_SCHEMA_VERSION, "generated_at": now, "enabled": enabled, "loading": loading,
        "replay_desk": replay_desk, "session": sess, "day_read": day_read.verdict(checks),
        "events": {"items": events.upcoming(clock.et(now).date(), bea=st.get("bea", now, 86400.0 * 2),
                                            earnings=st.get("earnings", now, 86400.0), biggest=biggest),
                   "bond_market": events.bond_market(clock.et(now).date())},
        "quotes": [tiles[s["id"]] for s in MARKET_QUOTES],
        "breadth": breadth_block,
        "sectors": sectors.board("sectors", params["sectors"], ctx),
        "industries": sectors.board("industries", params["industries"], ctx),
        "climate": clim,
        "top": sectors.top(params["top"], params["top_period"], ctx, runners),
        "sources": st.statuses(now),
    }
