"""The Cryptos page's smaller public feeds (ADR 040): sentiment, leverage, stablecoins and options expiries.

- alternative.me ``/fng/``: the Fear & Greed index, one reading a day, newest first (values are strings).
- Hyperliquid ``POST /info {"type": "metaAndAssetCtxs"}``: ``[meta, ctxs]`` index-aligned; ``funding`` is the
  hourly rate as a fraction, ``openInterest`` is in coins, ``markPx`` in dollars (``kPEPE`` is 1,000 PEPE).
- DefiLlama ``stablecoincharts/all``: one row a day of the USD-pegged supply (``totalCirculatingUSD``).
- Deribit ``get_book_summary_by_currency?kind=option``: every listed option with its open interest in coins;
  instrument names carry the expiry (``BTC-3OCT26-110000-C``).
Each parser raises ``SourceError`` on an answer it cannot read.
"""
from __future__ import annotations

import re
from itertools import pairwise
from datetime import date, datetime, timezone
from typing import Any

from constants_crypto import (
    CRYPTO_DERIBIT_URL,
    CRYPTO_FEAR_GREED_URL,
    CRYPTO_HYPERLIQUID_URL,
    CRYPTO_OPTIONS_EXPIRY_HOUR_UTC,
    CRYPTO_STABLES_CHART_URL,
    CRYPTO_STABLES_DAYS,
)
from crypto.web import SourceError, get_json, num, post_json

_MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}
_EXPIRY = re.compile(r"^(\d{1,2})([A-Z]{3})(\d{2})$")


# -- Fear & Greed -------------------------------------------------------------------------------------

def fetch_fear_greed() -> dict:
    return parse_fear_greed(get_json(CRYPTO_FEAR_GREED_URL, params={"limit": 8}))


def parse_fear_greed(body: Any) -> dict:
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise SourceError("alternative.me answered no readings")
    value = num(rows[0].get("value"))
    if value is None:
        raise SourceError("alternative.me's reading has no value")
    week = num(rows[7].get("value")) if len(rows) > 7 and isinstance(rows[7], dict) else None
    at = num(rows[0].get("timestamp"))
    return {"value": int(round(value)), "label": str(rows[0].get("value_classification") or "").strip() or None,
            "week_ago": int(round(week)) if week is not None else None, "at": at}


# -- Hyperliquid perpetuals ---------------------------------------------------------------------------

def fetch_perps() -> dict[str, dict]:
    return parse_perps(post_json(CRYPTO_HYPERLIQUID_URL, {"type": "metaAndAssetCtxs"}))


def parse_perps(body: Any) -> dict[str, dict]:
    """``{perp name: {funding_8h_pct, open_interest_usd}}``: the hourly rate x 8, in percent."""
    if not isinstance(body, list) or len(body) < 2:
        raise SourceError("Hyperliquid's answer is not [meta, contexts]")
    meta, ctxs = body[0], body[1]
    universe = meta.get("universe") if isinstance(meta, dict) else None
    if not isinstance(universe, list) or not isinstance(ctxs, list):
        raise SourceError("Hyperliquid's answer has no universe")
    out: dict[str, dict] = {}
    for asset, ctx in zip(universe, ctxs, strict=False):  # Hyperliquid aligns them; extra rows are skipped
        if not isinstance(asset, dict) or not isinstance(ctx, dict) or asset.get("isDelisted"):
            continue
        name = asset.get("name")
        if not isinstance(name, str):
            continue
        funding = num(ctx.get("funding"))
        oi = num(ctx.get("openInterest"))
        mark = num(ctx.get("markPx"))
        if mark is None:
            mark = num(ctx.get("oraclePx"))
        out[name] = {
            "funding_8h_pct": funding * 8 * 100 if funding is not None else None,
            "open_interest_usd": oi * mark if oi is not None and mark is not None else None,
        }
    if not out:
        raise SourceError("Hyperliquid listed no perpetuals")
    return out


# -- DefiLlama stablecoins ----------------------------------------------------------------------------

def fetch_stablecoins() -> dict:
    return parse_stablecoins(get_json(CRYPTO_STABLES_CHART_URL))


def parse_stablecoins(body: Any, days: int = CRYPTO_STABLES_DAYS) -> dict:
    """``{supply_usd, change_7d_usd, daily: [{date, net_usd}]}`` from the daily USD-pegged totals."""
    if not isinstance(body, list):
        raise SourceError("DefiLlama's stablecoin chart is not a list")
    totals: dict[int, float] = {}
    for row in body:
        if not isinstance(row, dict):
            continue
        ts = num(row.get("date"))
        block = row.get("totalCirculatingUSD") if isinstance(row.get("totalCirculatingUSD"), dict) \
            else row.get("totalCirculating")
        usd = num(block.get("peggedUSD")) if isinstance(block, dict) else None
        if ts is not None and usd is not None:
            totals[int(ts)] = usd
    if len(totals) < 2:
        raise SourceError("DefiLlama's stablecoin chart has no history")
    days_sorted = sorted(totals)
    supply = totals[days_sorted[-1]]
    week_ago = [d for d in days_sorted if d <= days_sorted[-1] - 7 * 86400]
    daily = []
    for prev, cur in pairwise(days_sorted[-(days + 1):]):
        daily.append({"date": datetime.fromtimestamp(cur, timezone.utc).date().isoformat(),
                      "net_usd": totals[cur] - totals[prev]})
    return {"supply_usd": supply, "change_7d_usd": supply - totals[week_ago[-1]] if week_ago else None,
            "daily": daily}


# -- Deribit options expiries -------------------------------------------------------------------------

def fetch_option_expiries(currency: str = "BTC") -> list[dict]:
    return parse_option_expiries(get_json(CRYPTO_DERIBIT_URL, params={"currency": currency, "kind": "option"}))


def parse_option_expiries(body: Any) -> list[dict]:
    """``[{at, open_interest, notional_usd}]`` per expiry, soonest first (``at`` is 08:00 UTC that day)."""
    rows = body.get("result") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise SourceError("Deribit's answer has no result")
    groups: dict[float, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        at = expiry_at(str(row.get("instrument_name") or ""))
        oi = num(row.get("open_interest"))
        und = num(row.get("underlying_price"))
        if at is None or oi is None:
            continue
        acc = groups.setdefault(at, [0.0, 0.0, 0.0])
        acc[0] += oi
        if und is not None:
            acc[1] += oi * und
            acc[2] += oi
    return [{"at": at, "open_interest": acc[0], "notional_usd": acc[1] if acc[2] > 0 else None}
            for at, acc in sorted(groups.items())]


def expiry_at(instrument: str) -> float | None:
    """08:00 UTC on the expiry an option name carries (``BTC-3OCT26-110000-C``), else ``None``."""
    parts = instrument.split("-")
    if len(parts) < 4:
        return None
    m = _EXPIRY.match(parts[1])
    if not m or m.group(2) not in _MONTHS:
        return None
    try:
        day = date(2000 + int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))
    except ValueError:
        return None
    return datetime(day.year, day.month, day.day, CRYPTO_OPTIONS_EXPIRY_HOUR_UTC, tzinfo=timezone.utc).timestamp()
