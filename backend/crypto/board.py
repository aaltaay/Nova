"""The Cryptos page's board (ADR 040): the stored answers composed into the wire shape of AGENTS.md section 3.

Pure over ``crypto.state``'s answers: no network, no IBKR. An answer that is missing or too old is ``None`` and
every number built on it is ``None`` -- unknown, never 0 and never another source's.
"""
from __future__ import annotations

from typing import Any

from constants_crypto import (
    CRYPTO_BETA_DAYS,
    CRYPTO_BETA_MIN_DAYS,
    CRYPTO_BRIDGE,
    CRYPTO_BRIDGE_DRIVERS,
    CRYPTO_BRIDGE_READ_BAND_PT,
    CRYPTO_CANDLES_TTL_SEC,
    CRYPTO_COINS,
    CRYPTO_CORR_DAYS,
    CRYPTO_CORR_SYMBOL,
    CRYPTO_GLOBAL_TTL_SEC,
    CRYPTO_HOURLY_TTL_SEC,
    CRYPTO_MARKETS_TTL_SEC,
    CRYPTO_NEWS_MAX,
    CRYPTO_NEWS_TTL_SEC,
    CRYPTO_NEXT_MAX,
    CRYPTO_NO_ETF_FLOWS_NOTE,
    CRYPTO_NO_LIQUIDATIONS_NOTE,
    CRYPTO_PERPS_TTL_SEC,
    CRYPTO_SCHEMA_VERSION,
    CRYPTO_SLOW_TTL_SEC,
    CRYPTO_VOLUME_HISTORY_TTL_SEC,
)
from crypto import clock, stats
from crypto.classify import KIND_CATALYST, KIND_NEGATIVE, best_item
from crypto.coinbase import price_at
from crypto.state import Store

# The reads whose first answer the page waits for before it stops saying "loading".
CORE_KEYS = ("markets", "global", "perps", "fear_greed")
_NEWS_RANK = {KIND_CATALYST: 0, KIND_NEGATIVE: 0}


def compose(st: Store, now: float, *, enabled: bool = True, replay_desk: bool = False) -> dict:
    markets = st.get("markets", now, CRYPTO_MARKETS_TTL_SEC) or {}
    perps = st.get("perps", now, CRYPTO_PERPS_TTL_SEC)
    headlines = st.get("news", now, CRYPTO_NEWS_TTL_SEC)
    coins = [_coin(st, now, c, markets, perps, headlines) for c in CRYPTO_COINS]
    ref_at, ref_day = clock.reference_close(now)
    drivers = {d: _driver(st, now, d, ref_at) for d in CRYPTO_BRIDGE_DRIVERS}
    return {
        "schema_version": CRYPTO_SCHEMA_VERSION,
        "generated_at": now,
        "enabled": enabled,
        "loading": enabled and _loading(st),
        "replay_desk": replay_desk,
        "clock": clock.clock(now),
        "market": _market(st, now, markets, coins, drivers),
        "coins": coins,
        "leverage": _leverage(coins, perps),
        "flows": {"etf": None, "etf_note": CRYPTO_NO_ETF_FLOWS_NOTE,
                  "stablecoins": st.get("stablecoins", now, CRYPTO_SLOW_TTL_SEC)},
        "bridge": _bridge(st, now, ref_at, ref_day, drivers),
        "next": _next(st, now),
        "news": _news(headlines),
        "sources": st.statuses(now),
    }


def _loading(st: Store) -> bool:
    since = st.wanted_since()
    return any(st.answered_at(k) is None and not st.tried_since(k, since) for k in CORE_KEYS)


def _coin(st: Store, now: float, coin: dict, markets: dict, perps: dict | None, headlines: dict | None) -> dict:
    sym = coin["symbol"]
    m = markets.get(coin["coingecko"]) or {}
    history = st.get(f"volume:{sym}", now, CRYPTO_VOLUME_HISTORY_TTL_SEC)
    avg = sum(history) / len(history) if history else None
    vol = m.get("volume_24h_usd")
    perp = (perps or {}).get(coin["perp"]) or {}
    items = (headlines or {}).get(sym) if headlines is not None else None
    why = best_item(items or [])
    return {
        "symbol": sym, "name": coin["name"], "rank": m.get("rank"), "price": m.get("price"),
        "high_24h": m.get("high_24h"), "low_24h": m.get("low_24h"),
        "change_1h_pct": m.get("change_1h_pct"), "change_24h_pct": m.get("change_24h_pct"),
        "change_7d_pct": m.get("change_7d_pct"), "volume_24h_usd": vol,
        "volume_x_30d": vol / avg if vol is not None and avg else None,
        "market_cap_usd": m.get("market_cap_usd"), "from_ath_pct": m.get("from_ath_pct"),
        "spark_7d": list(m.get("spark_7d") or []), "funding_8h_pct": perp.get("funding_8h_pct"),
        "groups": list(coin["groups"]),
        "why": None if why is None else {k: why.get(k) for k in ("kind", "title", "source", "published_ts", "url")},
        "news_checked": headlines is not None and items is not None,
        "ibkr": st.get(f"listing:{sym}", now, 1e12),
        "etf": coin["etf"], "chart": coin["coinbase"] is not None,
    }


def _market(st: Store, now: float, markets: dict, coins: list[dict], drivers: dict) -> dict:
    glob = st.get("global", now, CRYPTO_GLOBAL_TTL_SEC) or {}
    btc = markets.get("bitcoin") or {}
    eth = markets.get("ethereum") or {}
    return {
        "total_cap_usd": glob.get("total_cap_usd"),
        "total_cap_change_24h_pct": glob.get("total_cap_change_24h_pct"),
        "btc_dominance_pct": glob.get("btc_dominance_pct"),
        "btc_dominance_change_24h_pt": _dominance_change(glob, btc),
        "total_volume_usd": glob.get("total_volume_usd"),
        "volume_x_30d": _volume_x(st, now, coins),
        "fear_greed": st.get("fear_greed", now, CRYPTO_SLOW_TTL_SEC),
        "eth_btc": eth["price"] / btc["price"] if eth.get("price") and btc.get("price") else None,
        "eth_btc_change_24h_pct": _ratio_change(eth.get("change_24h_pct"), btc.get("change_24h_pct")),
        "btc_qqq_corr_30d": _qqq_corr(st, now, drivers.get("BTC")),
    }


def _dominance_change(glob: dict, btc: dict) -> float | None:
    """BTC's share now minus 24 hours ago, both from CoinGecko's own 24-hour changes."""
    total, total_chg = glob.get("total_cap_usd"), glob.get("total_cap_change_24h_pct")
    cap, cap_chg = btc.get("market_cap_usd"), btc.get("market_cap_change_24h_usd")
    if None in (total, total_chg, cap, cap_chg) or total <= 0 or total_chg <= -100:
        return None
    total_then = total / (1 + total_chg / 100)
    cap_then = cap - cap_chg
    if total_then <= 0 or cap_then <= 0:
        return None
    return (cap / total - cap_then / total_then) * 100


def _ratio_change(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b <= -100:
        return None
    return ((1 + a / 100) / (1 + b / 100) - 1) * 100


def _volume_x(st: Store, now: float, coins: list[dict]) -> float | None:
    """The listed coins' 24-hour volume over their own 30-day average (coins with both only)."""
    today = avg = 0.0
    for c in coins:
        history = st.get(f"volume:{c['symbol']}", now, CRYPTO_VOLUME_HISTORY_TTL_SEC)
        if history and c["volume_24h_usd"] is not None:
            today += c["volume_24h_usd"]
            avg += sum(history) / len(history)
    return today / avg if avg > 0 else None


def _leverage(coins: list[dict], perps: dict | None) -> dict:
    """Hyperliquid's funding per coin (high to low) and open interest; liquidations are a stated absence."""
    funding = sorted(({"symbol": c["symbol"], "funding_8h_pct": c["funding_8h_pct"]}
                      for c in coins if c["funding_8h_pct"] is not None), key=lambda f: -f["funding_8h_pct"])
    ois = [((perps or {}).get(c["perp"]) or {}).get("open_interest_usd") for c in CRYPTO_COINS]
    known = [oi for oi in ois if oi is not None]
    btc = (perps or {}).get("BTC") or {}
    return {"funding": funding, "open_interest_usd": sum(known) if known else None,
            "btc_open_interest_usd": btc.get("open_interest_usd"), "liquidations_24h": None,
            "liquidations_note": CRYPTO_NO_LIQUIDATIONS_NOTE}


def _driver(st: Store, now: float, symbol: str, ref_at: float) -> dict:
    """A bridge driver's (BTC / ETH) last price, its price at the reference close, and its 16:00 ET index."""
    c15 = st.get(f"candles:{symbol}:15m", now, CRYPTO_CANDLES_TTL_SEC["15m"]) or []
    hourly = st.get(f"hourly:{symbol}", now, CRYPTO_HOURLY_TTL_SEC) or []
    last = c15[-1]["c"] if c15 else None
    at_close = price_at(c15, ref_at, 900)
    if at_close is None:
        at_close = price_at(hourly, ref_at, 3600)
    return {"last": last, "at_close": at_close, "since_pct": stats.pct_change(last, at_close), "hourly": hourly}


def _bridge(st: Store, now: float, ref_at: float, ref_day: str, drivers: dict) -> dict:
    quotes = st.get("bridge_quotes", now, 0.0)
    closes_by = {b["symbol"]: st.get(f"closes:{b['symbol']}", now, 1e12) or {} for b in CRYPTO_BRIDGE}
    days = sorted({d for closes in closes_by.values() for d in closes})
    coin_closes = {d: stats.prices_at_close(v["hourly"], days) for d, v in drivers.items()}
    rows = []
    for b in CRYPTO_BRIDGE:
        closes = closes_by[b["symbol"]]
        close = closes.get(ref_day)
        last = (quotes or {}).get(b["symbol"])
        xs, ys = stats.aligned_returns(closes, coin_closes[b["driver"]], CRYPTO_BETA_DAYS)
        beta = stats.beta(xs, ys, CRYPTO_BETA_MIN_DAYS)
        since = stats.pct_change(last, close)
        move = drivers[b["driver"]]["since_pct"]
        implied = move * beta if move is not None and beta is not None else None
        gap = since - implied if since is not None and implied is not None else None
        read = None if gap is None else ("in_line" if abs(gap) <= CRYPTO_BRIDGE_READ_BAND_PT
                                         else "ahead" if gap > 0 else "behind")
        rows.append({"symbol": b["symbol"], "what": b["what"], "driver": b["driver"], "beta": beta,
                     "close": close, "last": last, "since_close_pct": since, "implied_pct": implied,
                     "read": read, "gap_pt": gap})
    ibkr = next((s for s in st.statuses(now) if s["id"] == "ibkr"), None) or {}
    return {"reference_close_at": ref_at, "phase": clock.bridge_phase(now),
            "btc_since_close_pct": drivers["BTC"]["since_pct"], "eth_since_close_pct": drivers["ETH"]["since_pct"],
            "rows": rows, "error": ibkr.get("error")}


def _qqq_corr(st: Store, now: float, btc: dict | None) -> float | None:
    closes = st.get(f"closes:{CRYPTO_CORR_SYMBOL}", now, 1e12) or {}
    if not btc or not closes:
        return None
    coin = stats.prices_at_close(btc["hourly"], sorted(closes))
    xs, ys = stats.aligned_returns(closes, coin, CRYPTO_CORR_DAYS)
    return stats.corr(xs, ys, CRYPTO_BETA_MIN_DAYS)


def _next(st: Store, now: float) -> list[dict]:
    funding = clock.next_funding(now)
    day = clock.crypto_day_start(now) + clock.DAY
    events = [{"at": funding, "kind": "funding", "title": "Funding settles",
               "detail": "The 8-hour futures exchanges settle funding at 00:00, 08:00 and 16:00 UTC."}]
    events.append({"at": day, "kind": "crypto_day", "title": "New crypto day",
                   "detail": "Daily candles and 24-hour changes on most sites reset at 00:00 UTC."})
    stock = clock.stock_next(now)
    events.append({"at": stock["at"], "kind": "stocks", "title": stock["title"], "detail": None})
    exp_at, monthly = clock.next_expiry(now)
    expiries = st.get("expiries", now, CRYPTO_SLOW_TTL_SEC) or []
    match = next((e for e in expiries if abs(e["at"] - exp_at) < 1), None)
    notional = match.get("notional_usd") if match else None
    events.append({"at": exp_at, "kind": "expiry",
                   "title": "Monthly options expiry" if monthly else "Weekly options expiry",
                   "detail": f"BTC {_usd_short(notional)} open on Deribit" if notional else None})
    events.sort(key=lambda e: e["at"])
    if funding == day:  # 00:00 UTC: the crypto day and a funding settlement at once
        events = [e for e in events if e["kind"] != "funding"]
        for e in events:
            if e["kind"] == "crypto_day":
                e["title"] = "New crypto day · funding settles"
    return events[:CRYPTO_NEXT_MAX]


def _news(headlines: dict | None) -> list[dict]:
    if not headlines:
        return []
    seen: dict[str, dict] = {}
    for sym, items in headlines.items():
        for it in items:
            key = it["title"].lower()
            if key not in seen:
                seen[key] = {"published_ts": it["published_ts"], "symbol": sym, "kind": it["kind"],
                             "title": it["title"], "source": it.get("source"), "url": it.get("url")}
    ranked = sorted(seen.values(), key=lambda n: (_NEWS_RANK.get(n["kind"], 1), -n["published_ts"]))
    return ranked[:CRYPTO_NEWS_MAX]


def _usd_short(value: Any) -> str:
    v = float(value)
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:,.0f}"
