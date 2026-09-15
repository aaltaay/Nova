"""TradingAgents-style market snapshot: Yahoo first, optional vendor keys.

Never reads IBKR L1 / depth / tape. Missing optional keys stay honest.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    chunk = closes[-window:]
    return sum(chunk) / window


def _rsi(closes: list[float], window: int = 14) -> float | None:
    if len(closes) <= window:
        return None
    gains = 0.0
    losses = 0.0
    for prev, nxt in zip(closes[-window - 1 : -1], closes[-window:], strict=False):
        delta = nxt - prev
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    if losses == 0:
        return 100.0
    rs = (gains / window) / (losses / window)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(closes: list[float]) -> dict[str, float | None]:
    if len(closes) < 26:
        return {"macd": None, "signal": None}
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    if ema12 is None or ema26 is None:
        return {"macd": None, "signal": None}
    macd = ema12 - ema26
    return {"macd": macd, "signal": None}


def _ema(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    k = 2 / (window + 1)
    ema = sum(values[:window]) / window
    for price in values[window:]:
        ema = price * k + ema * (1 - k)
    return ema


def _yahoo_snapshot(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    info: dict[str, Any] = {}
    try:
        info = ticker.info or {}
    except Exception as exc:
        logger.warning("advise yahoo info failed for %s: %s", symbol, exc)
    hist_rows: list[dict[str, Any]] = []
    closes: list[float] = []
    try:
        hist = ticker.history(period="6mo", interval="1d")
        if hist is not None and not hist.empty:
            for ts, row in hist.tail(80).iterrows():
                close = _num(row.get("Close"))
                if close is None:
                    continue
                closes.append(close)
                hist_rows.append(
                    {
                        "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                        "close": close,
                        "volume": _num(row.get("Volume")),
                    }
                )
    except Exception as exc:
        logger.warning("advise yahoo history failed for %s: %s", symbol, exc)
    headlines: list[str] = []
    try:
        news = ticker.news or []
        for item in news[:12]:
            title = (item.get("title") or item.get("headline") or "").strip()
            if title:
                headlines.append(title)
    except Exception as exc:
        logger.warning("advise yahoo news failed for %s: %s", symbol, exc)
    last = closes[-1] if closes else _num(info.get("regularMarketPrice"))
    prev = closes[-2] if len(closes) > 1 else _num(info.get("previousClose"))
    change_pct = None
    if last is not None and prev:
        change_pct = (last - prev) / prev * 100
    return {
        "source": "yahoo",
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "last": last,
        "previous_close": prev,
        "change_pct": change_pct,
        "market_cap": _num(info.get("marketCap")),
        "pe": _num(info.get("trailingPE")),
        "forward_pe": _num(info.get("forwardPE")),
        "eps": _num(info.get("trailingEps")),
        "float_shares": _num(info.get("floatShares")),
        "short_percent": _num(info.get("shortPercentOfFloat")),
        "fifty_two_week_high": _num(info.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _num(info.get("fiftyTwoWeekLow")),
        "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50),
        "rsi14": _rsi(closes),
        "macd": _macd(closes),
        "recent_closes": hist_rows[-10:],
        "headlines": headlines,
    }


def _finnhub_headlines(symbol: str) -> tuple[list[str], str]:
    key = (os.environ.get("FINNHUB_API_KEY") or "").strip()
    if not key:
        return [], "optional FINNHUB_API_KEY missing -- Yahoo headlines only"
    url = (
        "https://finnhub.io/api/v1/company-news?"
        + urllib.parse.urlencode({"symbol": symbol, "from": "2020-01-01", "to": "2100-01-01"})
    )
    request = urllib.request.Request(url, headers={"X-Finnhub-Token": key})
    try:
        with urllib.request.urlopen(request, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], f"Finnhub news failed: {exc}"
    if not isinstance(payload, list):
        return [], "Finnhub news returned a non-list"
    titles = []
    for item in payload[:12]:
        if isinstance(item, dict):
            title = str(item.get("headline") or "").strip()
            if title:
                titles.append(title)
    return titles, "Finnhub company-news attached"


def vendor_status() -> dict[str, str]:
    return {
        "OPENROUTER_API_KEY": "required for a new debate (not for book reopen)",
        "FINNHUB_API_KEY": (
            "optional -- richer news for the News/Sentiment analysts"
            if not (os.environ.get("FINNHUB_API_KEY") or "").strip()
            else "set"
        ),
        "ALPHA_VANTAGE_API_KEY": "optional -- not required; Yahoo covers technicals",
        "REDDIT_CLIENT_ID": "optional -- social sentiment; skipped when unset",
    }


def gather(symbol: str) -> dict[str, Any]:
    snap = _yahoo_snapshot(symbol)
    extra, note = _finnhub_headlines(symbol)
    headlines = list(snap.get("headlines") or [])
    for title in extra:
        if title not in headlines:
            headlines.append(title)
    snap["headlines"] = headlines[:16]
    snap["vendor_notes"] = [note]
    if not (os.environ.get("REDDIT_CLIENT_ID") or "").strip():
        snap["vendor_notes"].append(
            "optional Reddit keys missing -- sentiment uses headlines only"
        )
    snap["vendors"] = vendor_status()
    return snap


def render_brief(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, default=str, indent=2)[:8000]
