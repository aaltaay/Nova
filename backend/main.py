from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv, set_key
import requests
from datetime import datetime, date
import math
import time
import asyncio
import json
from zoneinfo import ZoneInfo
import yfinance as yf
import websockets

from constants import (
    CLOSED_INTERVAL_SEC,
    DISCOVERY_INTERVAL_SEC,
    FOCUS_INTERVAL_SEC,
    GAINERS_INTERVAL_SEC,
    GAPPER_MIN_GAP_PCT,
    SCAN_CAP_DEFAULT,
    TOP_N_DEFAULT,
)

load_dotenv()

_BLAST_REV = "4"
_ET = ZoneInfo("America/New_York")
_DATA_URL = "https://data.alpaca.markets"

# Scan intervals — authoritative values in `constants.py`
_DISCOVERY_INTERVAL = DISCOVERY_INTERVAL_SEC
_FOCUS_INTERVAL = FOCUS_INTERVAL_SEC
_GAINERS_INTERVAL = GAINERS_INTERVAL_SEC
_CLOSED_INTERVAL = CLOSED_INTERVAL_SEC

_SCAN_CAP = int(os.environ.get("ALPACA_SCAN_SYMBOL_CAP", str(SCAN_CAP_DEFAULT)))
_MIN_GAP_PCT = float(os.environ.get("BLAST_MIN_GAP_PCT", str(GAPPER_MIN_GAP_PCT)))
_TOP_N = int(os.environ.get("BLAST_TOP_N", str(TOP_N_DEFAULT)))

# ── Assets cache (1-hour TTL) ─────────────────────────────────────────────────
_assets_cache: list[str] = []
_assets_cache_ts: float = 0.0
_ASSETS_CACHE_TTL = 3600.0

# ── Gapper cache (pre-market) ─────────────────────────────────────────────────
_gapper_cache: list[dict] = []
_gapper_cache_ts: float = 0.0
_last_discovery_ts: float = 0.0

# ── Gainers cache (market hours) ──────────────────────────────────────────────
_gainer_cache: list[dict] = []
_gainer_cache_ts: float = 0.0

# ── Losers cache (market hours) ───────────────────────────────────────────────
_loser_cache: list[dict] = []
_loser_cache_ts: float = 0.0

# ── Average daily volume cache (reset each day, lazy-filled for RVOL) ─────────
_avg_volume_cache: dict[str, float] = {}
_avg_volume_date: str = ""

# ── Fundamentals cache (15-min TTL, keyed by symbol) ──────────────────────────
_fundamentals_cache: dict[str, dict] = {}
_fundamentals_cache_ts: dict[str, float] = {}
_FUNDAMENTALS_CACHE_TTL = 900.0  # 15 minutes

# ── Health + mode ──────────────────────────────────────────────────────────────
_cached_health: dict = {"status": "loading", "latency_ms": 0}
_current_mode: str = "closed"   # "premarket" | "market" | "closed"

# ── WebSocket streaming state ──────────────────────────────────────────────────
# The WS stream receives real-time trades and updates _gapper_cache / _gainer_cache
# in-place, decoupling price freshness from the REST scan cadence.
_ws_subscribed: set[str] = set()   # symbols the WS is currently subscribed to
_ws_needs_resub: bool = False       # scan loop sets True when symbol list changes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    if v is None:
        return None
    return v.strip().strip("'\"")


def _alpaca_headers() -> dict[str, str] | None:
    api_key = _env("APCA_API_KEY_ID")
    api_secret = _env("APCA_API_SECRET_KEY")
    if not api_key or not api_secret:
        return None
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}


def _now_et() -> datetime:
    return datetime.now(_ET)


def _in_premarket() -> bool:
    now = _now_et()
    start = now.replace(hour=4, minute=0, second=0, microsecond=0)
    open_ = now.replace(hour=9, minute=30, second=0, microsecond=0)
    return start <= now < open_


def _in_market_hours() -> bool:
    now = _now_et()
    open_ = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_ <= now < close


def _get_feed() -> str:
    return (_env("ALPACA_DATA_FEED") or "sip").lower()


# ── Fundamentals (yfinance / Yahoo Finance) ───────────────────────────────────

def _fetch_fundamentals(symbol: str) -> dict:
    """Fetch fundamental data for a single symbol via yfinance with TTL caching."""
    global _fundamentals_cache, _fundamentals_cache_ts
    now = time.monotonic()
    cached_ts = _fundamentals_cache_ts.get(symbol, 0.0)
    if symbol in _fundamentals_cache and (now - cached_ts) < _FUNDAMENTALS_CACHE_TTL:
        return _fundamentals_cache[symbol]
    try:
        info = yf.Ticker(symbol).info
        fundamentals = {
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "float_shares": info.get("floatShares"),
            "short_interest": info.get("sharesShort"),
            "short_ratio": info.get("shortRatio"),
            "short_percent_of_float": info.get("shortPercentOfFloat"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
        }
        _fundamentals_cache[symbol] = fundamentals
        _fundamentals_cache_ts[symbol] = now
        return fundamentals
    except Exception:
        empty: dict = {
            "market_cap": None, "shares_outstanding": None, "float_shares": None,
            "short_interest": None, "short_ratio": None, "short_percent_of_float": None,
            "pe_ratio": None, "forward_pe": None, "eps": None, "sector": None,
            "industry": None, "fifty_two_week_high": None, "fifty_two_week_low": None,
            "dividend_yield": None, "beta": None,
        }
        _fundamentals_cache[symbol] = empty
        _fundamentals_cache_ts[symbol] = now
        return empty


def _fetch_fundamentals_batch(symbols: list[str]) -> None:
    """Populate the fundamentals cache for a list of symbols (skips already-cached ones)."""
    now = time.monotonic()
    missing = [
        s for s in symbols
        if s not in _fundamentals_cache
        or (now - _fundamentals_cache_ts.get(s, 0.0)) >= _FUNDAMENTALS_CACHE_TTL
    ]
    for sym in missing:
        _fetch_fundamentals(sym)


# ── Tradable assets ───────────────────────────────────────────────────────────

def _get_tradable_symbols(base_url: str, headers: dict) -> list[str]:
    """Fetch active US equity symbols, capped and cached for one hour."""
    global _assets_cache, _assets_cache_ts
    now = time.monotonic()
    if _assets_cache and (now - _assets_cache_ts) < _ASSETS_CACHE_TTL:
        return _assets_cache
    try:
        resp = requests.get(
            f"{base_url}/v2/assets",
            headers=headers,
            params={"status": "active", "asset_class": "us_equity"},
            timeout=20,
        )
        if resp.status_code != 200:
            return _assets_cache
        tradable = [a["symbol"] for a in resp.json() if a.get("tradable")]
        _assets_cache = tradable[:_SCAN_CAP]
        _assets_cache_ts = now
        return _assets_cache
    except Exception:
        return _assets_cache


# ── Snapshots ─────────────────────────────────────────────────────────────────

def _fetch_snapshots(symbols: list[str], headers: dict) -> dict:
    """Fetch snapshots for a list of symbols in batches of 100."""
    result: dict = {}
    feed = _get_feed()
    for i in range(0, len(symbols), 100):
        chunk = symbols[i: i + 100]
        try:
            resp = requests.get(
                f"{_DATA_URL}/v2/stocks/snapshots",
                headers=headers,
                params={"symbols": ",".join(chunk), "feed": feed},
                timeout=15,
            )
            if resp.status_code == 200:
                result.update(resp.json())
        except Exception:
            continue
    return result


# ── Average daily volume ──────────────────────────────────────────────────────

def _ensure_avg_volume(symbols: list[str], headers: dict) -> None:
    """Lazily populate avg_volume_cache for any symbols not yet cached today."""
    global _avg_volume_cache, _avg_volume_date
    today = date.today().isoformat()
    if _avg_volume_date != today:
        _avg_volume_cache = {}
        _avg_volume_date = today
    missing = [s for s in symbols if s not in _avg_volume_cache]
    if not missing:
        return
    feed = _get_feed()
    for i in range(0, len(missing), 100):
        chunk = missing[i: i + 100]
        try:
            resp = requests.get(
                f"{_DATA_URL}/v2/stocks/bars",
                headers=headers,
                params={"symbols": ",".join(chunk), "timeframe": "1Day", "limit": 20, "feed": feed},
                timeout=20,
            )
            if resp.status_code != 200:
                continue
            bars_data = resp.json().get("bars", {})
            for sym, bars in bars_data.items():
                vols = [b.get("v", 0) for b in bars if b.get("v", 0) > 0]
                if vols:
                    _avg_volume_cache[sym] = sum(vols) / len(vols)
        except Exception:
            continue


# ── News ──────────────────────────────────────────────────────────────────────

def _check_news(symbols: list[str], headers: dict) -> dict[str, str]:
    """Return dict mapping symbol -> newest article created_at (ISO string) for articles today (ET date)."""
    if not symbols:
        return {}
    today = _now_et().date().isoformat()
    try:
        resp = requests.get(
            f"{_DATA_URL}/v1beta1/news",
            headers=headers,
            params={"symbols": ",".join(symbols[:50]), "start": today, "limit": 50},
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        out: dict[str, str] = {}
        for article in resp.json().get("news", []):
            created_at = article.get("created_at", "")
            for s in article.get("symbols", []):
                # Keep the most recent created_at per symbol
                if s not in out or created_at > out[s]:
                    out[s] = created_at
        return out
    except Exception:
        return {}


# ── Health ping ───────────────────────────────────────────────────────────────

def _ping_health(base_url: str, headers: dict) -> bool:
    global _cached_health
    start = datetime.now()
    try:
        r = requests.get(f"{base_url}/v2/account", headers=headers, timeout=5)
        latency = math.floor((datetime.now() - start).total_seconds() * 1000)
        if r.status_code == 200:
            _cached_health = {"status": "connected", "latency_ms": latency}
            return True
        _cached_health = {"status": "error", "latency_ms": latency,
                          "message": f"Alpaca HTTP {r.status_code}: {(r.text or '')[:200]}"}
        return False
    except Exception as e:
        _cached_health = {"status": "disconnected", "latency_ms": 0, "message": str(e)}
        return False


# ── Gapper helpers ────────────────────────────────────────────────────────────

def _gapper_meets_min_gap(gap_frac: float | None) -> bool:
    """True if gap as a fraction (e.g. 0.1 = 10%) is at or above the configured floor."""
    if gap_frac is None:
        return False
    return gap_frac * 100 >= _MIN_GAP_PCT


def _prune_gappers_below_min(gappers: list[dict]) -> list[dict]:
    return [g for g in gappers if _gapper_meets_min_gap(g.get("gap_percent"))]


def _compute_gappers(snaps: dict) -> list[dict]:
    gappers: list[dict] = []
    for sym, snap in snaps.items():
        latest_trade = snap.get("latestTrade") or {}
        prev_bar = snap.get("prevDailyBar") or {}
        daily_bar = snap.get("dailyBar") or {}
        price = latest_trade.get("p", 0)
        prev_close = prev_bar.get("c", 0)
        volume = daily_bar.get("v", 0)
        if not price or not prev_close:
            continue
        gap_frac = (price - prev_close) / prev_close
        if not _gapper_meets_min_gap(gap_frac):
            continue
        gappers.append({
            "symbol": sym,
            "previous_close": prev_close,
            "current_price": price,
            "gap_percent": gap_frac,
            "volume": volume,
        })
    gappers.sort(key=lambda x: x["gap_percent"], reverse=True)
    return gappers[:_TOP_N]


def _enrich_gappers(gappers: list[dict], news: dict[str, str]) -> list[dict]:
    symbols = [g["symbol"] for g in gappers]
    _fetch_fundamentals_batch(symbols)
    for g in gappers:
        sym = g["symbol"]
        avg_vol = _avg_volume_cache.get(sym)
        vol = g["volume"]
        g["rel_volume"] = round(vol / avg_vol, 2) if avg_vol and avg_vol > 0 and vol > 0 else None
        g["has_news"] = sym in news
        g["newest_headline_at"] = news.get(sym)
        fund = _fundamentals_cache.get(sym, {})
        g["market_cap"] = fund.get("market_cap")
        g["float"] = fund.get("float_shares")
        g["short_interest"] = fund.get("short_interest")
        g["short_ratio"] = fund.get("short_ratio")
    return gappers


# ── WebSocket helpers ─────────────────────────────────────────────────────────

def _ws_mark_resub() -> None:
    """Signal the WebSocket loop to sync subscriptions on next iteration."""
    global _ws_needs_resub
    _ws_needs_resub = True


def _ws_current_symbols() -> set[str]:
    """Return the union of all symbols currently in the gapper, gainer, and loser caches."""
    syms: set[str] = set()
    for g in _gapper_cache:
        syms.add(g["symbol"])
    for g in _gainer_cache:
        syms.add(g["symbol"])
    for g in _loser_cache:
        syms.add(g["symbol"])
    return syms


def _apply_trade_to_mover_list(cache: list[dict], sym: str, price: float) -> bool:
    """Update price/change fields for a symbol in a mover list (gainers or losers). Returns True if found."""
    for i, g in enumerate(cache):
        if g["symbol"] == sym:
            prev_close = g.get("prev_close") or 0.0
            if prev_close:
                new_change_abs = price - prev_close
                new_change_pct = new_change_abs / prev_close
            else:
                new_change_abs = g.get("change_abs", 0)
                new_change_pct = g.get("change_pct", 0)
            cache[i] = {
                **g,
                "price": price,
                "change_abs": new_change_abs,
                "change_pct": new_change_pct,
            }
            return True
    return False


def _handle_trade(msg: dict) -> None:
    """Apply a real-time trade message to the in-memory caches."""
    global _gapper_cache, _gapper_cache_ts, _gainer_cache, _gainer_cache_ts, _loser_cache, _loser_cache_ts
    sym = msg.get("S")
    price = msg.get("p")
    if not sym or not price:
        return
    now = time.time()

    # Update gappers — only during pre-market; after 9:30 the list is preserved as-is.
    if _current_mode == "premarket":
        for i, g in enumerate(_gapper_cache):
            if g["symbol"] == sym:
                prev_close = g["previous_close"]
                new_gap = (price - prev_close) / prev_close if prev_close else g["gap_percent"]
                if not _gapper_meets_min_gap(new_gap):
                    del _gapper_cache[i]
                else:
                    _gapper_cache[i] = {**g, "current_price": price, "gap_percent": new_gap}
                _gapper_cache_ts = now
                break

    # Update gainers — always apply.
    if _apply_trade_to_mover_list(_gainer_cache, sym, price):
        _gainer_cache_ts = now

    # Update losers — always apply.
    if _apply_trade_to_mover_list(_loser_cache, sym, price):
        _loser_cache_ts = now


# ── Pre-market scan functions ─────────────────────────────────────────────────

def _run_discovery_scan() -> None:
    """Full universe scan: fetch all ~800 symbols, filter gappers, enrich."""
    global _gapper_cache, _gapper_cache_ts, _last_discovery_ts
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return
    if not _ping_health(base_url, headers):
        return

    symbols = _get_tradable_symbols(base_url, headers)
    if not symbols:
        return

    snaps = _fetch_snapshots(symbols, headers)
    gappers = _compute_gappers(snaps)
    gapper_syms = [g["symbol"] for g in gappers]
    _ensure_avg_volume(gapper_syms, headers)
    news = _check_news(gapper_syms, headers)
    gappers = _enrich_gappers(gappers, news)

    _gapper_cache = gappers
    _gapper_cache_ts = time.time()      # wall-clock for frontend display
    _last_discovery_ts = time.monotonic()  # monotonic for internal TTL check
    _ws_mark_resub()  # notify WebSocket loop to subscribe to newly discovered symbols


def _run_focus_scan() -> None:
    """Re-price only current gapper candidates (fast 20-sec refresh)."""
    global _gapper_cache, _gapper_cache_ts
    if not _gapper_cache:
        _run_discovery_scan()
        return
    headers = _alpaca_headers()
    if not headers:
        return

    symbols = [g["symbol"] for g in _gapper_cache]
    snaps = _fetch_snapshots(symbols, headers)
    if not snaps:
        return
    news = _check_news(symbols, headers)

    updated: list[dict] = []
    for g in _gapper_cache:
        sym = g["symbol"]
        snap = snaps.get(sym)
        if not snap:
            updated.append(g)
            continue
        latest_trade = snap.get("latestTrade") or {}
        prev_bar = snap.get("prevDailyBar") or {}
        daily_bar = snap.get("dailyBar") or {}
        price = latest_trade.get("p") or g["current_price"]
        prev_close = prev_bar.get("c") or g["previous_close"]
        volume = daily_bar.get("v") or g["volume"]
        gap_frac = (price - prev_close) / prev_close if price and prev_close else g["gap_percent"]
        avg_vol = _avg_volume_cache.get(sym)
        updated.append({
            **g,
            "current_price": price,
            "gap_percent": gap_frac,
            "volume": volume,
            "rel_volume": round(volume / avg_vol, 2) if avg_vol and avg_vol > 0 and volume > 0 else None,
            "has_news": sym in news,
            "newest_headline_at": news.get(sym),
        })

    updated.sort(key=lambda x: x["gap_percent"], reverse=True)
    updated = _prune_gappers_below_min(updated)
    _gapper_cache = updated
    _gapper_cache_ts = time.time()


# ── Market-hours gainers ──────────────────────────────────────────────────────

def _build_mover_entry(raw: dict, snaps: dict, premarket_gap_map: dict) -> dict:
    """Build an enriched mover dict from a raw movers API item and snapshot data."""
    sym = raw["symbol"]
    snap = snaps.get(sym, {})
    daily_bar = snap.get("dailyBar") or {}
    prev_bar = snap.get("prevDailyBar") or {}
    volume = daily_bar.get("v", 0)
    prev_close = prev_bar.get("c", 0)

    if sym in premarket_gap_map and premarket_gap_map[sym] is not None:
        gap_pct = premarket_gap_map[sym]
    elif prev_close:
        open_price = daily_bar.get("o", 0)
        gap_pct = (open_price - prev_close) / prev_close if open_price and prev_close else None
    else:
        gap_pct = None

    avg_vol = _avg_volume_cache.get(sym)
    fund = _fundamentals_cache.get(sym, {})
    return {
        "symbol": sym,
        "price": raw.get("price", 0),
        "change_pct": raw.get("percent_change", 0) / 100.0,
        "change_abs": raw.get("change", 0),
        "volume": volume,
        "gap_percent": gap_pct,
        "rel_volume": round(volume / avg_vol, 2) if avg_vol and avg_vol > 0 and volume > 0 else None,
        "has_news": False,   # filled in by caller after news check
        "newest_headline_at": None,
        "market_cap": fund.get("market_cap"),
        "float": fund.get("float_shares"),
        "short_interest": fund.get("short_interest"),
        "short_ratio": fund.get("short_ratio"),
        "prev_close": prev_close,
    }


def _run_gainers_update() -> None:
    """Fetch top gainers and losers via Alpaca Screener Movers API, enrich with snapshots + RVOL + news."""
    global _gainer_cache, _gainer_cache_ts, _loser_cache, _loser_cache_ts
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return
    if not _ping_health(base_url, headers):
        return

    # 1. Movers API — 1 call, returns top N gainers AND losers market-wide
    try:
        resp = requests.get(
            f"{_DATA_URL}/v1beta1/screener/stocks/movers",
            headers=headers,
            params={"top": min(_TOP_N, 50)},   # endpoint max is 50
            timeout=10,
        )
        if resp.status_code != 200:
            return
        movers_json = resp.json()
        gainers_raw = movers_json.get("gainers", [])
        losers_raw = movers_json.get("losers", [])
    except Exception:
        return

    if not gainers_raw and not losers_raw:
        return

    all_symbols = list({r["symbol"] for r in gainers_raw + losers_raw})

    # 2. Snapshot enrichment — 1 call for all mover symbols
    snaps = _fetch_snapshots(all_symbols, headers)

    # 3. Average volume for RVOL (lazy, cached per day)
    _ensure_avg_volume(all_symbols, headers)

    # 4. News check — 1 call covering all symbols
    news = _check_news(all_symbols, headers)

    # 5. Fetch fundamentals for all mover symbols
    _fetch_fundamentals_batch(all_symbols)

    # 6. Build enriched lists
    premarket_gap_map = {g["symbol"]: g.get("gap_percent") for g in _gapper_cache}

    gainers: list[dict] = []
    for raw in gainers_raw:
        entry = _build_mover_entry(raw, snaps, premarket_gap_map)
        sym = entry["symbol"]
        entry["has_news"] = sym in news
        entry["newest_headline_at"] = news.get(sym)
        gainers.append(entry)

    losers: list[dict] = []
    for raw in losers_raw:
        entry = _build_mover_entry(raw, snaps, premarket_gap_map)
        sym = entry["symbol"]
        entry["has_news"] = sym in news
        entry["newest_headline_at"] = news.get(sym)
        losers.append(entry)

    _gainer_cache = gainers
    _gainer_cache_ts = time.time()
    _loser_cache = losers
    _loser_cache_ts = time.time()
    _ws_mark_resub()  # notify WebSocket loop to subscribe to newly discovered symbols


# ── WebSocket streaming loop ──────────────────────────────────────────────────

async def _ws_stream_loop() -> None:
    """Persistent WebSocket connection to Alpaca's real-time SIP feed.

    Subscribes to trades for all symbols in the gapper/gainer caches and
    applies each trade message to the in-memory cache instantly, giving the
    frontend sub-second price freshness on every 1s poll.

    Auto-reconnects with exponential backoff on any failure.
    """
    global _ws_subscribed, _ws_needs_resub
    backoff = 1.0

    while True:
        try:
            api_key = _env("APCA_API_KEY_ID")
            api_secret = _env("APCA_API_SECRET_KEY")
            if not api_key or not api_secret:
                await asyncio.sleep(10)
                continue

            feed = _get_feed()
            url = f"wss://stream.data.alpaca.markets/v2/{feed}"

            async with websockets.connect(url, ping_interval=20, open_timeout=15) as ws:
                # Receive the initial "connected" banner
                await ws.recv()

                # Authenticate
                await ws.send(json.dumps({"action": "auth", "key": api_key, "secret": api_secret}))
                auth_msgs = json.loads(await ws.recv())
                if not any(m.get("T") == "success" and m.get("msg") == "authenticated"
                           for m in auth_msgs):
                    # Auth failed — back off and retry (keys may have just changed)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    continue

                # Successfully connected and authenticated — reset backoff
                backoff = 1.0
                _ws_subscribed = set()
                _ws_needs_resub = True  # subscribe to whatever is cached right now

                while True:
                    # Sync subscriptions whenever the scan loop adds/removes symbols
                    if _ws_needs_resub:
                        _ws_needs_resub = False
                        wanted = _ws_current_symbols()
                        to_add = wanted - _ws_subscribed
                        to_remove = _ws_subscribed - wanted
                        if to_add:
                            await ws.send(json.dumps({"action": "subscribe", "trades": list(to_add)}))
                        if to_remove:
                            await ws.send(json.dumps({"action": "unsubscribe", "trades": list(to_remove)}))
                        _ws_subscribed = wanted

                    # Wait for the next message (1s timeout lets us check _ws_needs_resub)
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msgs = json.loads(raw)
                        for msg in msgs:
                            if msg.get("T") == "t":
                                _handle_trade(msg)
                    except asyncio.TimeoutError:
                        pass  # no message arrived; loop back to check resub flag

        except asyncio.CancelledError:
            raise
        except Exception:
            _ws_subscribed = set()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


# ── Background scan loop ──────────────────────────────────────────────────────

async def _scan_loop() -> None:
    global _current_mode
    loop = asyncio.get_event_loop()
    while True:
        try:
            if _in_premarket():
                _current_mode = "premarket"
                mono = time.monotonic()
                if not _gapper_cache or (mono - _last_discovery_ts) > _DISCOVERY_INTERVAL:
                    await loop.run_in_executor(None, _run_discovery_scan)
                else:
                    await loop.run_in_executor(None, _run_focus_scan)
                await asyncio.sleep(_FOCUS_INTERVAL)
            elif _in_market_hours():
                _current_mode = "market"
                await loop.run_in_executor(None, _run_gainers_update)
                await asyncio.sleep(_GAINERS_INTERVAL)
            else:
                _current_mode = "closed"
                await loop.run_in_executor(None, _run_discovery_scan)
                await loop.run_in_executor(None, _run_gainers_update)
                await asyncio.sleep(_CLOSED_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ping Alpaca health immediately at startup so the frontend never sits on
    # "loading" status during closed-market hours when no scan would run.
    loop = asyncio.get_event_loop()
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if headers:
        await loop.run_in_executor(None, lambda: _ping_health(base_url, headers))
    scan_task = asyncio.create_task(_scan_loop())
    ws_task = asyncio.create_task(_ws_stream_loop())
    yield
    scan_task.cancel()
    ws_task.cancel()
    for t in (scan_task, ws_task):
        try:
            await t
        except asyncio.CancelledError:
            pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="B.L.A.S.T. API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConfigUpdate(BaseModel):
    api_key: str
    api_secret: str
    base_url: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return _cached_health


@app.get("/api/config")
def get_config():
    return {
        "api_key": _env("APCA_API_KEY_ID") or "",
        "api_secret": _env("APCA_API_SECRET_KEY") or "",
        "base_url": _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets",
    }


@app.post("/api/config")
def update_config(config: ConfigUpdate):
    global _assets_cache_ts, _last_discovery_ts
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    set_key(env_path, "APCA_API_KEY_ID", config.api_key)
    set_key(env_path, "APCA_API_SECRET_KEY", config.api_secret)
    set_key(env_path, "APCA_API_BASE_URL", config.base_url)
    load_dotenv(env_path, override=True)
    _assets_cache_ts = 0.0
    _last_discovery_ts = 0.0
    return {"status": "success"}


@app.get("/api/mode")
def get_mode():
    return {
        "mode": _current_mode,
        "health": _cached_health,
        "last_gapper_scan": _gapper_cache_ts,
        "last_gainer_scan": _gainer_cache_ts,
    }


@app.get("/api/gappers")
def get_gappers():
    """Pre-market gapper list. Returns cached data instantly."""
    return {
        "rev": _BLAST_REV,
        "mode": _current_mode,
        "health": _cached_health,
        "gappers": _gapper_cache,
        "last_scan": _gapper_cache_ts,
    }


@app.get("/api/gainers")
def get_gainers():
    """Market-hours top gainers list. Returns cached data instantly."""
    return {
        "rev": _BLAST_REV,
        "mode": _current_mode,
        "health": _cached_health,
        "gainers": _gainer_cache,
        "last_scan": _gainer_cache_ts,
    }


@app.get("/api/movers")
def get_movers():
    """Top gainers and losers from the Alpaca screener. Returns cached data instantly."""
    return {
        "rev": _BLAST_REV,
        "mode": _current_mode,
        "health": _cached_health,
        "gainers": _gainer_cache,
        "losers": _loser_cache,
        "last_scan": _gainer_cache_ts,
    }


@app.get("/api/ticker/{symbol}")
def get_ticker_detail(symbol: str):
    """Fetch full detail for a single symbol: asset info, snapshot, news, avg volume."""
    symbol = symbol.upper()
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return {"error": "API keys not configured"}

    feed = _get_feed()

    # 1. Asset info from Trading API
    asset: dict = {}
    try:
        r = requests.get(f"{base_url}/v2/assets/{symbol}", headers=headers, timeout=10)
        if r.status_code == 200:
            a = r.json()
            asset = {
                "name": a.get("name", ""),
                "exchange": a.get("exchange", ""),
                "asset_class": a.get("class", ""),
                "tradable": a.get("tradable", False),
                "marginable": a.get("marginable", False),
                "shortable": a.get("shortable", False),
                "easy_to_borrow": a.get("easy_to_borrow", False),
                "fractionable": a.get("fractionable", False),
                "maintenance_margin_requirement": a.get("maintenance_margin_requirement"),
            }
    except Exception:
        pass

    # 2. Single-symbol snapshot
    snapshot: dict = {}
    try:
        r = requests.get(
            f"{_DATA_URL}/v2/stocks/{symbol}/snapshot",
            headers=headers,
            params={"feed": feed},
            timeout=10,
        )
        if r.status_code == 200:
            raw = r.json()

            def _bar(b: dict | None) -> dict | None:
                if not b:
                    return None
                return {
                    "open": b.get("o"),
                    "high": b.get("h"),
                    "low": b.get("l"),
                    "close": b.get("c"),
                    "volume": b.get("v"),
                    "trade_count": b.get("n"),
                    "vwap": b.get("vw"),
                    "timestamp": b.get("t"),
                }

            lt = raw.get("latestTrade") or {}
            lq = raw.get("latestQuote") or {}
            snapshot = {
                "latest_trade": {
                    "price": lt.get("p"),
                    "size": lt.get("s"),
                    "exchange": lt.get("x"),
                    "timestamp": lt.get("t"),
                } if lt else None,
                "latest_quote": {
                    "bid_price": lq.get("bp"),
                    "bid_size": lq.get("bs"),
                    "ask_price": lq.get("ap"),
                    "ask_size": lq.get("as"),
                    "timestamp": lq.get("t"),
                } if lq else None,
                "minute_bar": _bar(raw.get("minuteBar")),
                "daily_bar": _bar(raw.get("dailyBar")),
                "prev_daily_bar": _bar(raw.get("prevDailyBar")),
            }
    except Exception:
        pass

    # 3. News articles (up to 10)
    news: list[dict] = []
    try:
        today = _now_et().date().isoformat()
        r = requests.get(
            f"{_DATA_URL}/v1beta1/news",
            headers=headers,
            params={"symbols": symbol, "start": today, "limit": 10},
            timeout=10,
        )
        if r.status_code == 200:
            for article in r.json().get("news", []):
                news.append({
                    "headline": article.get("headline", ""),
                    "summary": article.get("summary", ""),
                    "author": article.get("author", ""),
                    "source": article.get("source", ""),
                    "url": article.get("url", ""),
                    "created_at": article.get("created_at", ""),
                    "symbols": article.get("symbols", []),
                    "images": article.get("images", []),
                })
    except Exception:
        pass

    # 4. Average volume from cache (may be None if not yet populated)
    avg_vol = _avg_volume_cache.get(symbol)
    if avg_vol is None:
        _ensure_avg_volume([symbol], headers)
        avg_vol = _avg_volume_cache.get(symbol)

    daily_vol = (snapshot.get("daily_bar") or {}).get("volume") or 0
    rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else None

    # 5. Fundamentals via yfinance
    fundamentals = _fetch_fundamentals(symbol)

    return {
        "symbol": symbol,
        "asset": asset,
        "snapshot": snapshot,
        "avg_volume": avg_vol,
        "rel_volume": rel_vol,
        "news": news,
        "fundamentals": fundamentals,
    }
