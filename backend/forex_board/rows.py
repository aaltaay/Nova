"""Each currency's row on the Forex page's wire (ADR 061; shape in architecture/schema/forex-board.md), from memory.

A row holds the currency's BIS size, its price (spot, or its future when IBKR has no spot quote), its futures money,
how busy its day is against a normal one, and its home session. Strength, the sessions and the "mixed" flag need every
currency's move, so ``board`` adds them. Unknown is ``null`` with the reason -- IBKR's refusal, the read's own failure,
or "waiting for IBKR" -- never a guess.
"""
from __future__ import annotations

from collections.abc import Mapping

from constants_forex_board import (
    FOREX_BIS_TOTAL_USD,
    FOREX_NORMAL_DAYS,
    FOREX_PERIOD_DAYS,
    FOREX_QUOTE_FRESH_SEC,
)
from forex_board import clock, contracts, jobs, money, prices
from forex_board.state import Store

WAITING = "waiting for IBKR"


def _r(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def why(st: Store, key: str) -> str:
    failed = st.failure(key)
    return failed[0] if failed else WAITING


def refusals(st: Store, cur: Mapping, now: float) -> list[dict]:
    out = []
    for kind, spec in (("spot", contracts.spot_spec(cur)), ("future", contracts.future_spec(cur))):
        got = jobs.refused(st, contracts.key(kind, spec), now) if spec else None
        if got:
            out.append({"instrument": got.get("instrument"), "error": got.get("error")})
    return out


def _today(st: Store, key: str, fx: Mapping, now: float) -> dict | None:
    value = st.get(key, now)
    return value if value and value.get("fx_from") == fx["from"] else None


def _quote(quotes: Mapping, quotes_at: float | None, code: str, fx: Mapping, now: float) -> dict | None:
    q = quotes.get(code) or {}
    if not fx["open"] or q.get("mid") is None or quotes_at is None or now - quotes_at > FOREX_QUOTE_FRESH_SEC:
        return None
    return q


def _price(basis: str | None, instrument: dict | None, pair: str | None, per_usd: bool, open_level: float | None,
           now_level: float | None, at: float | None, data_type: str | None, error: str | None) -> dict:
    """The wire's ``price``; a future priced in dollars per unit is shown as the pair the market quotes."""
    pct = prices.pair_pct(now_level, open_level)
    vs = prices.vs_usd(pct, per_usd)
    # a future in dollars per unit (6L) shown as the market's per-dollar pair (USD/BRL); an inverted one already is
    show_inverse = basis == "future" and not per_usd and pair is not None and pair.startswith("USD/")
    rate = (1.0 / now_level) if show_inverse and now_level else now_level
    opened = (1.0 / open_level) if show_inverse and open_level else open_level
    pair_move = prices.vs_usd(vs, True) if show_inverse else pct
    return {"basis": basis if pct is not None else None, "instrument": instrument, "pair": pair, "rate": _r(rate, 6),
            "open": _r(opened, 6), "pair_pct": _r(pair_move), "vs_usd_pct": _r(vs),
            "at": at if pct is not None else None, "data_type": data_type if pct is not None else None,
            "error": None if pct is not None else error}


def today_levels(st: Store, cur: Mapping, now: float, fx: Mapping, quotes: Mapping,
                 quotes_at: float | None) -> dict | None:
    """The currency's FX day: ``{basis, per_usd, open, now, closes, high, low, at, data_type, instrument}`` from its
    spot pair (the quote now, else the newest hour), else its future. ``None`` with neither."""
    code = cur["code"]
    spot = contracts.spot_spec(cur)
    hourly = _today(st, f"hourly:{code}", fx, now) if spot else None
    if hourly and hourly["day"].get("open"):
        day = hourly["day"]
        q = _quote(quotes, quotes_at, code, fx, now)
        level = q["mid"] if q else day.get("last")
        if level is None:
            return None
        high = max(v for v in (day.get("high"), level) if v is not None)
        low = min(v for v in (day.get("low"), level) if v is not None)
        return {"basis": "spot", "per_usd": spot["per_usd"], "open": day["open"], "now": level,
                "closes": day["closes"], "high": high, "low": low, "at": q["at"] if q else hourly["read_at"],
                "data_type": q.get("data_type") if q else None, "instrument": hourly["instrument"], "pair": spot["quote"]}
    fut = contracts.future_spec(cur)
    flow = _today(st, f"flow:{code}", fx, now) if fut else None
    lv = (flow or {}).get("levels") or {}
    if not lv.get("open") or not lv.get("last"):
        return None
    return {"basis": "future", "per_usd": bool(fut["inverted"]), "open": lv["open"], "now": lv["last"],
            "closes": lv.get("closes") or [None] * 24, "high": lv.get("high"), "low": lv.get("low"),
            "at": flow["read_at"], "data_type": None, "instrument": flow["instrument"],
            "pair": spot["quote"] if spot else fut["code"]}


def _no_price(st: Store, cur: Mapping, now: float, spot_key: str, future_key: str) -> str:
    """Why a currency has no price: IBKR's refusal of its pair (with no future to fall back on), else the read it
    waits on."""
    spot = contracts.spot_spec(cur)
    refused = jobs.refused(st, contracts.key("spot", spot), now) if spot else None
    if refused and not cur.get("future"):
        return refused.get("error") or "IBKR refused this pair"
    if spot and not refused:
        return why(st, spot_key)
    return why(st, future_key)


def _price_1d(st: Store, cur: Mapping, now: float, today: dict | None) -> dict:
    spot = contracts.spot_spec(cur)
    pair = spot["quote"] if spot else None
    if today is None:
        error = _no_price(st, cur, now, f"hourly:{cur['code']}", f"flow:{cur['code']}")
        return _price(None, None, pair, bool(spot and spot["per_usd"]), None, None, None, None, error)
    return _price(today["basis"], today["instrument"], today["pair"], today["per_usd"], today["open"], today["now"],
                  today["at"], today["data_type"], None)


def _completed(st: Store, key: str, fx: Mapping, now: float) -> list[dict]:
    value = st.get(key, now)
    return prices.completed((value or {}).get("rows") or [], fx["date"], fx["open"])


def _price_days(st: Store, cur: Mapping, now: float, fx: Mapping, period: str) -> dict:
    code = cur["code"]
    spot = contracts.spot_spec(cur)
    days = FOREX_PERIOD_DAYS[period]
    if spot:
        got = prices.period_move(_completed(st, f"daily:{code}", fx, now), days)
        if got:
            daily = st.get(f"daily:{code}", now)
            return _price("spot", daily["instrument"], spot["quote"], spot["per_usd"], got["open"], got["rate"],
                          daily["read_at"], None, None)
    fut = contracts.future_spec(cur)
    if fut:
        got = prices.period_move(_completed(st, f"flow_daily:{code}", fx, now), days)
        if got:
            daily = st.get(f"flow_daily:{code}", now)
            return _price("future", daily["instrument"], spot["quote"] if spot else fut["code"], bool(fut["inverted"]),
                          got["open"], got["rate"], daily["read_at"], None, None)
    error = _no_price(st, cur, now, f"daily:{code}", f"flow_daily:{code}")
    return _price(None, None, spot["quote"] if spot else None, bool(spot and spot["per_usd"]), None, None, None, None,
                  error)


def _futures(st: Store, cur: Mapping, now: float, fx: Mapping, period: str) -> dict:
    code = cur["code"]
    fut = contracts.future_spec(cur)
    empty = {"basis": None, "instrument": None, "inverted": None, "traded_usd": None, "up_usd": None, "down_usd": None,
             "pressure_usd": None, "pressure_pct": None, "contracts": None, "last_bar_at": None, "at": None,
             "error": None, "refused": refusals(st, cur, now)}
    if not fut:
        return {**empty, "error": "no CME future"}
    if period == "1D":
        flow = _today(st, f"flow:{code}", fx, now)
        if flow is None:
            return {**empty, "error": why(st, f"flow:{code}")}
        s, at, last = flow["sums"], flow["read_at"], flow["sums"].get("last_bar_at")
    else:
        rows = _completed(st, f"flow_daily:{code}", fx, now)[-FOREX_PERIOD_DAYS[period]:]
        daily = st.get(f"flow_daily:{code}", now)
        if not rows or daily is None:
            return {**empty, "error": why(st, f"flow_daily:{code}")}
        spot_rows = _completed(st, f"daily:{code}", fx, now)
        spot = contracts.spot_spec(cur)
        signs = (money.day_signs(spot_rows, spot["per_usd"]) if spot and spot_rows
                 else money.day_signs(_completed(st, f"flow_daily:{code}", fx, now), bool(fut["inverted"])))
        mult = (daily["instrument"] or {}).get("multiplier") or float(fut["multiplier"])
        s, at, last = money.daily_sums(rows, signs, mult, bool(fut["inverted"])), daily["read_at"], None
        flow = daily
    return {**empty, "basis": "future", "instrument": flow["instrument"], "inverted": bool(fut["inverted"]),
            "traded_usd": _r(s["traded"], 2), "up_usd": _r(s["up"], 2), "down_usd": _r(s["down"], 2),
            "pressure_usd": _r(s["up"] - s["down"], 2), "pressure_pct": money.pressure_pct(s["up"], s["down"], s["traded"]),
            "contracts": _r(s["contracts"], 2), "last_bar_at": last, "at": at}


def dollar_futures(rows: list[dict]) -> dict:
    """The dollar's futures: the other side of every currency's future."""
    got = [r["futures"] for r in rows if r["code"] != "USD" and r["futures"].get("traded_usd") is not None]
    traded = sum(f["traded_usd"] for f in got)
    up = sum(f["down_usd"] for f in got)            # a currency sold against the dollar is the dollar bought
    down = sum(f["up_usd"] for f in got)
    return {"basis": "sum" if got else None, "instrument": None, "inverted": None,
            "traded_usd": _r(traded, 2) if got else None, "up_usd": _r(up, 2) if got else None,
            "down_usd": _r(down, 2) if got else None, "pressure_usd": _r(up - down, 2) if got else None,
            "pressure_pct": money.pressure_pct(up, down, traded) if got else None, "contracts": None,
            "last_bar_at": max((f["last_bar_at"] or 0.0 for f in got), default=None) or None,
            "at": max((f["at"] or 0.0 for f in got), default=None) or None,
            "error": None if got else WAITING, "refused": []}


def _activity(st: Store, cur: Mapping, now: float, fx: Mapping, today: dict | None) -> tuple[float | None, float | None]:
    code = cur["code"]
    range_x = None
    if today:
        key = f"daily:{code}" if today["basis"] == "spot" else f"flow_daily:{code}"
        range_x = prices.range_x(today["high"], today["low"], today["open"], _completed(st, key, fx, now),
                                 FOREX_NORMAL_DAYS)
    volume_x = None
    flow = _today(st, f"flow:{code}", fx, now) if cur.get("future") else None
    if flow:
        normal = money.normal_volume(_completed(st, f"flow_daily:{code}", fx, now), FOREX_NORMAL_DAYS)
        contracts_today = flow["sums"].get("contracts")
        volume_x = round(contracts_today / normal, 2) if normal and contracts_today is not None else None
    return range_x, volume_x


def currency(st: Store, cur: Mapping, now: float, fx: Mapping, period: str, quotes: Mapping,
             quotes_at: float | None) -> tuple[dict, dict | None]:
    """The row (strength, sessions and the flag still to add) and the currency's FX day for the board's path."""
    code = cur["code"]
    today = None if code == "USD" else today_levels(st, cur, now, fx, quotes, quotes_at)
    if code == "USD":
        price = {"basis": "spot", "instrument": None, "pair": None, "rate": None, "open": None, "pair_pct": 0.0,
                 "vs_usd_pct": 0.0, "at": quotes_at, "data_type": None, "error": None}
        futures: dict = {}
    else:
        price = _price_1d(st, cur, now, today) if period == "1D" else _price_days(st, cur, now, fx, period)
        futures = _futures(st, cur, now, fx, period)
    range_x, volume_x = _activity(st, cur, now, fx, today) if code != "USD" else (None, None)
    row = {
        "code": code, "name": cur["name"], "city": cur["city"], "lat": cur["lat"], "lon": cur["lon"], "tz": cur["tz"],
        "home": clock.home(cur["tz"], now, fx),
        "size": {"usd": cur["bis_usd"], "share_pct": round(cur["bis_usd"] / FOREX_BIS_TOTAL_USD * 100.0, 2),
                 "rank": cur["rank"], "pair": cur["pair"], "pair_usd": cur["pair_usd"]},
        "price": price, "strength_pct": None, "by_session": None, "range_x": range_x, "volume_x": volume_x,
        "futures": futures, "mixed": False,
    }
    return row, today
