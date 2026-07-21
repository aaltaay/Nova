"""
Scanner helper functions — stateless.

Extracted from ``main.py`` to comply with the 200-line main.py target.

All functions here are import-safe and depend on explicit modules. Functions
that need environment-derived scanner configuration retrieve it from the typed
runtime-state provider.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests

from alpaca import (
    ALPACA_DATA_URL as _DATA_URL,
    _get_feed,
    _try_fallback_to_iex,
)
from constants import (
    EXCLUDED_NAME_KEYWORDS,
    RVOL_LOOKBACK_DAYS,
    SCANNER_MIN_PRICE,
    SNAPSHOT_WORKERS,
    SYMBOL_EXCLUDE_RE,
)
from market import ET as _ET, now_et as _now_et
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)


# ── Snapshot fetcher ──────────────────────────────────────────────────────────

def _fetch_snapshots(symbols: list[str], headers: dict) -> dict:
    """Fetch Alpaca snapshots for a list of symbols in parallel batches of 100.

    Uses a thread pool so large universes (~4 000 symbols = ~40 batches)
    complete in ~1 s instead of ~8 s sequential.
    """
    if not symbols:
        return {}
    feed = _get_feed()
    chunks = [symbols[i: i + 100] for i in range(0, len(symbols), 100)]

    def _fetch_chunk(chunk: list[str]) -> dict:
        try:
            resp = requests.get(
                f"{_DATA_URL}/v2/stocks/snapshots",
                headers=headers,
                params={"symbols": ",".join(chunk), "feed": feed},
                timeout=15,
            )
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            logger.warning("_fetch_snapshots chunk network error (%d syms)", len(chunk), exc_info=True)
            return {}

    result: dict = {}
    failed_futures = 0
    with ThreadPoolExecutor(max_workers=SNAPSHOT_WORKERS) as pool:
        futures = {pool.submit(_fetch_chunk, c): c for c in chunks}
        for fut in as_completed(futures):
            try:
                result.update(fut.result())
            except Exception:
                failed_futures += 1
                logger.warning("_fetch_snapshots future failed", exc_info=True)
                continue
    if not result and chunks:
        logger.error(
            "_fetch_snapshots: all %d chunk(s) empty/failed for %d symbols",
            len(chunks),
            len(symbols),
        )
    elif failed_futures:
        logger.warning(
            "_fetch_snapshots: %d/%d futures failed; partial result size=%d",
            failed_futures,
            len(chunks),
            len(result),
        )
    return result


# ── News lookup ───────────────────────────────────────────────────────────────

def _check_news(symbols: list[str], headers: dict) -> dict[str, str]:
    """Return {symbol: newest_article_created_at} for today's articles (ET date)."""
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
                if s not in out or created_at > out[s]:
                    out[s] = created_at
        return out
    except Exception:
        logger.warning("_check_news failed for %s", symbols[:10], exc_info=True)
        return {}


# ── Prev-close helper ─────────────────────────────────────────────────────────

def _pick_prev_close(snap: dict) -> float:
    """Return the correct 'previous regular-session close' from an Alpaca snapshot dict.

    Alpaca's bar semantics differ by session:
      - Pre-market (before 9:30 ET): dailyBar is the *last completed* regular session
        (yesterday). prevDailyBar is the session before that (two days ago).
      - Market/after-hours: dailyBar is today's developing/completed bar.
        prevDailyBar is yesterday's completed bar.

    We detect which case we're in by comparing dailyBar's timestamp date to today.
    If dailyBar is from a prior date → it IS yesterday's close → return dailyBar.c.
    Otherwise → dailyBar is today's bar → yesterday's close is prevDailyBar.c.
    """
    daily_bar = snap.get("dailyBar") or {}
    prev_bar = snap.get("prevDailyBar") or {}
    daily_ts = daily_bar.get("t")
    if daily_ts:
        try:
            ts = datetime.fromisoformat(daily_ts.replace("Z", "+00:00"))
            if ts.astimezone(_ET).date() < _now_et().date():
                return daily_bar.get("c") or 0
        except (ValueError, AttributeError):
            return prev_bar.get("c") or 0
    return prev_bar.get("c") or 0


# ── Asset filter ──────────────────────────────────────────────────────────────

def _is_common_stock(asset: dict) -> bool:
    """Single source of truth: should this Alpaca asset appear in any scan?

    All symbol-exclusion rules live here. To add a new exclusion, add it here.
    To remove one, remove it here. No other function should make this decision.
    """
    import hod_momo as _hod_momo
    if get_runtime_state().config.require_tradable and not asset.get("tradable"):
        return False
    sym = asset.get("symbol", "")
    if SYMBOL_EXCLUDE_RE.search(sym):
        return False
    name = (asset.get("name") or "").lower()
    if any(kw.lower() in name for kw in EXCLUDED_NAME_KEYWORDS):
        return False
    if _hod_momo.is_blocked(sym):
        return False
    return True


# ── Gapper compute helpers ────────────────────────────────────────────────────

def _gapper_meets_min_gap(gap_frac: float | None) -> bool:
    """True if gap as a fraction (e.g. 0.1 = 10%) meets the configured floor."""
    if gap_frac is None:
        return False
    return gap_frac * 100 >= get_runtime_state().config.min_gap_pct


def _prune_gappers_below_min(gappers: list[dict]) -> list[dict]:
    return [g for g in gappers if _gapper_meets_min_gap(g.get("gap_percent"))]


def _compute_gappers(snaps: dict, ref_bar_key: str = "prevDailyBar") -> list[dict]:
    """Compute gap entries from Alpaca snapshot data.

    ``ref_bar_key`` controls the reference close price:
    - ``"prevDailyBar"`` (default): gap vs previous session close — pre-market.
      Uses ``_pick_prev_close()`` which detects whether ``dailyBar`` is yesterday's
      or today's bar, resolving the Alpaca pre-market bar ambiguity.
    - ``"dailyBar"``: gap vs today's regular-session close — after-hours.
    """
    gappers: list[dict] = []
    for sym, snap in snaps.items():
        latest_trade = snap.get("latestTrade") or {}
        daily_bar = snap.get("dailyBar") or {}
        price = latest_trade.get("p") or daily_bar.get("c", 0)
        if ref_bar_key == "prevDailyBar":
            prev_close = _pick_prev_close(snap)
        else:
            prev_close = (snap.get(ref_bar_key) or {}).get("c", 0)
        volume = daily_bar.get("v", 0)
        if not price or not prev_close:
            continue
        if price < SCANNER_MIN_PRICE:
            continue
        gap_frac = (price - prev_close) / prev_close
        if not _gapper_meets_min_gap(gap_frac):
            continue
        change_abs = price - prev_close
        change_pct = gap_frac
        gappers.append({
            "symbol": sym,
            "price": price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "change_abs": change_abs,
            "previous_close": prev_close,
            "current_price": price,
            "gap_percent": gap_frac,
            "volume": volume,
        })
    gappers.sort(key=lambda x: x["gap_percent"], reverse=True)
    return gappers[:get_runtime_state().config.top_n]


# ── Avg-volume fetcher (stateless: callers pass + own the cache dict) ─────────

def fetch_avg_volume_batch(
    symbols: list[str],
    headers: dict,
    cache: dict,
) -> None:
    """Fetch daily-bar average volume for ``symbols`` missing from ``cache``.

    Writes directly into the caller-supplied ``cache`` dict so the caller
    retains ownership of the cache lifecycle (reset, TTL, etc.).  This keeps
    ``scanner.py`` stateless — no module-level dicts to rebind.
    """
    missing = [s for s in symbols if s not in cache]
    if not missing:
        return
    feed = _get_feed()
    for i in range(0, len(missing), 100):
        chunk = missing[i: i + 100]
        try:
            resp = requests.get(
                f"{_DATA_URL}/v2/stocks/bars",
                headers=headers,
                params={
                    "symbols": ",".join(chunk),
                    "timeframe": "1Day",
                    "limit": RVOL_LOOKBACK_DAYS,
                    "start": (date.today() - timedelta(days=45)).isoformat(),
                    "end": date.today().isoformat(),
                    "feed": feed,
                },
                timeout=20,
            )
            if resp.status_code == 403 and "sip" in resp.text.lower():
                if _try_fallback_to_iex("avg_volume bars 403 SIP rejection"):
                    feed = _get_feed()
                    resp = requests.get(
                        f"{_DATA_URL}/v2/stocks/bars",
                        headers=headers,
                        params={
                            "symbols": ",".join(chunk),
                            "timeframe": "1Day",
                            "limit": RVOL_LOOKBACK_DAYS,
                            "start": (date.today() - timedelta(days=45)).isoformat(),
                            "end": date.today().isoformat(),
                            "feed": feed,
                        },
                        timeout=20,
                    )
                    if resp.status_code != 200:
                        logger.warning(
                            "avg_volume bars returned %s after IEX fallback: %s",
                            resp.status_code, resp.text[:200],
                        )
                        continue
                else:
                    logger.warning(
                        "avg_volume bars returned %s: %s", resp.status_code, resp.text[:200]
                    )
                    continue
            elif resp.status_code != 200:
                logger.warning(
                    "avg_volume bars returned %s: %s", resp.status_code, resp.text[:200]
                )
                continue
            bars_data = resp.json().get("bars", {})
            for sym, bars in bars_data.items():
                vols = [b.get("v", 0) for b in bars if b.get("v", 0) > 0]
                if vols:
                    cache[sym] = sum(vols) / len(vols)
        except Exception:
            logger.exception("avg_volume fetch failed for chunk %s", chunk)
