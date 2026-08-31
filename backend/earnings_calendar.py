"""Finnhub earnings calendar -- date/session windowing for the Earnings tab.

Owner of ``EARNINGS_CALENDAR_CACHE_FILE`` (persisted-state.mdc). Invalidation
trigger: TTL expiry (``EARNINGS_CALENDAR_TTL_SEC``) or an explicit
``EARNINGS_CALENDAR_SCHEMA_VERSION`` bump. On a cold process start the last
good snapshot is read from disk so a restart does not need to wait on
Finnhub before the tab has rows.

The widest window ("This month") is fetched and cached once per TTL; the
narrower ranges (today / tomorrow / week) are derived in-memory from that
same snapshot instead of issuing a second Finnhub call per range.

Only exposes what Finnhub's free ``/calendar/earnings`` endpoint actually
returns (symbol, date, session, EPS/revenue estimate + actual). Implied
move, IV, and surprise-% are NOT computed here -- they need an options chain
Nova does not fetch. Do not invent a formula for them.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, timedelta

import requests

from constants import (
    EARNINGS_CALENDAR_CACHE_FILE,
    EARNINGS_CALENDAR_HTTP_TIMEOUT_SEC,
    EARNINGS_CALENDAR_RANGES,
    EARNINGS_CALENDAR_SCHEMA_VERSION,
    EARNINGS_CALENDAR_TTL_SEC,
    EARNINGS_CALENDAR_WINDOW_DAYS,
    FINNHUB_EARNINGS_URL,
)
from market import now_et

logger = logging.getLogger(__name__)

_SESSION_MAP = {"bmo": "bmo", "amc": "amc", "dmh": "intraday"}
_RANGE_MAX_OFFSET_DAYS = {
    "today": 0,
    "tomorrow": 1,
    "week": 6,
    "month": EARNINGS_CALENDAR_WINDOW_DAYS - 1,
}

_cache_rows: list[dict] | None = None
_cache_ts: float = 0.0  # wall-clock time.time() -- must survive a restart


def _session_for(hour: str | None) -> str:
    return _SESSION_MAP.get((hour or "").strip().lower(), "intraday")


def _window_dates(today: date) -> tuple[date, date]:
    return today, today + timedelta(days=EARNINGS_CALENDAR_WINDOW_DAYS)


def _fetch_finnhub(date_from: str, date_to: str, api_key: str) -> list[dict] | None:
    try:
        resp = requests.get(
            FINNHUB_EARNINGS_URL,
            params={"from": date_from, "to": date_to, "token": api_key},
            timeout=EARNINGS_CALENDAR_HTTP_TIMEOUT_SEC,
        )
    except Exception:
        logger.warning("earnings_calendar: Finnhub request failed", exc_info=True)
        return None
    if resp.status_code != 200:
        logger.warning(
            "earnings_calendar: Finnhub returned %s for %s..%s",
            resp.status_code, date_from, date_to,
        )
        return None
    try:
        payload = resp.json()
    except Exception:
        logger.warning("earnings_calendar: Finnhub response not JSON", exc_info=True)
        return None
    raw = payload.get("earningsCalendar")
    if not isinstance(raw, list):
        return []
    rows: list[dict] = []
    for item in raw:
        symbol = str(item.get("symbol") or "").strip().upper()
        event_date = item.get("date")
        if not symbol or not event_date:
            continue
        rows.append({
            "symbol": symbol,
            "date": event_date,
            "session": _session_for(item.get("hour")),
            "eps_estimate": item.get("epsEstimate"),
            "eps_actual": item.get("epsActual"),
            "revenue_estimate": item.get("revenueEstimate"),
            "revenue_actual": item.get("revenueActual"),
            "quarter": item.get("quarter"),
            "year": item.get("year"),
        })
    return rows


def _load_disk_snapshot() -> tuple[list[dict], float]:
    try:
        with open(EARNINGS_CALENDAR_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], 0.0
    except Exception:
        logger.warning("earnings_calendar: disk snapshot unreadable", exc_info=True)
        return [], 0.0
    if int(data.get("schema_version") or 0) != EARNINGS_CALENDAR_SCHEMA_VERSION:
        logger.warning(
            "earnings_calendar: refusing disk snapshot with unknown schema_version=%s",
            data.get("schema_version"),
        )
        return [], 0.0
    rows = data.get("rows")
    if not isinstance(rows, list):
        return [], 0.0
    return rows, float(data.get("ts") or 0.0)


def _save_disk_snapshot(rows: list[dict], ts: float) -> None:
    try:
        directory = os.path.dirname(EARNINGS_CALENDAR_CACHE_FILE)
        os.makedirs(directory, exist_ok=True)
        tmp = EARNINGS_CALENDAR_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"schema_version": EARNINGS_CALENDAR_SCHEMA_VERSION, "ts": ts, "rows": rows},
                f,
            )
        os.replace(tmp, EARNINGS_CALENDAR_CACHE_FILE)
    except Exception:
        logger.warning("earnings_calendar: failed to persist snapshot", exc_info=True)


def _ensure_loaded_from_disk() -> None:
    global _cache_rows, _cache_ts
    if _cache_rows is not None:
        return
    rows, ts = _load_disk_snapshot()
    _cache_rows = rows
    _cache_ts = ts


def get_calendar_rows(*, force: bool = False) -> tuple[list[dict], float, str | None]:
    """Return ``(rows, as_of_ts, error)`` for the widest cached window.

    ``error`` is a user-facing string when Finnhub could not be reached and
    there is no usable stale snapshot -- callers must not treat an empty
    list as "no earnings this week" in that case.
    """
    global _cache_rows, _cache_ts
    _ensure_loaded_from_disk()

    now = time.time()
    fresh = _cache_rows is not None and (now - _cache_ts) < EARNINGS_CALENDAR_TTL_SEC
    if fresh and not force:
        return _cache_rows, _cache_ts, None

    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        if _cache_rows:
            return _cache_rows, _cache_ts, None
        return [], 0.0, "FINNHUB_API_KEY is not set -- Earnings calendar has no data source."

    start, end = _window_dates(now_et().date())
    fetched = _fetch_finnhub(start.isoformat(), end.isoformat(), api_key)
    if fetched is None:
        if _cache_rows:
            logger.warning("earnings_calendar: Finnhub fetch failed -- serving stale snapshot")
            return _cache_rows, _cache_ts, None
        return [], 0.0, "Finnhub earnings calendar request failed and no cached snapshot exists."

    _cache_rows = fetched
    _cache_ts = now
    _save_disk_snapshot(fetched, now)
    return fetched, now, None


def _decorate(row: dict) -> dict:
    """Attach company name / sector / market cap from the yfinance cache only.

    Read-only, no network -- mirrors ``mover_enrich_view.decorate_rows``.
    A cold cache leaves these ``None``; ``earnings_enrich_hooks.warm`` fills
    it in the background for the next poll.
    """
    from fundamentals import _fundamentals_cache

    fund = _fundamentals_cache.get(row["symbol"]) or {}
    out = dict(row)
    out["company_name"] = fund.get("company_name")
    out["sector"] = fund.get("sector")
    out["market_cap"] = fund.get("market_cap")
    return out


def _day_label(d: date, today: date) -> str:
    offset = (d - today).days
    weekday_date = f"{d.strftime('%a %b')} {d.day}"
    if offset == 0:
        return f"Today · {weekday_date}"
    if offset == 1:
        return f"Tomorrow · {weekday_date}"
    return weekday_date


def build_earnings_view(range_key: str) -> dict:
    """Day-grouped BMO/AMC/intraday lanes for one range (1c layout)."""
    if range_key not in EARNINGS_CALENDAR_RANGES:
        range_key = "today"
    rows, as_of, error = get_calendar_rows()
    today = now_et().date()
    end = today + timedelta(days=_RANGE_MAX_OFFSET_DAYS[range_key])

    by_date: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        try:
            d = date.fromisoformat(str(row["date"]))
        except (ValueError, TypeError, KeyError):
            continue
        if d < today or d > end:
            continue
        bucket = by_date.setdefault(row["date"], {"bmo": [], "amc": [], "intraday": []})
        bucket[row["session"]].append(_decorate(row))

    today_symbols = [r["symbol"] for r in rows if r.get("date") == today.isoformat()]
    if today_symbols:
        from earnings_enrich_hooks import warm as _warm_fundamentals
        _warm_fundamentals(today_symbols)

    days = []
    for date_str in sorted(by_date.keys()):
        d = date.fromisoformat(date_str)
        lanes = by_date[date_str]
        for lane_rows in lanes.values():
            lane_rows.sort(key=lambda r: r["symbol"])
        days.append({
            "date": date_str,
            "label": _day_label(d, today),
            "count": sum(len(v) for v in lanes.values()),
            "bmo": lanes["bmo"],
            "amc": lanes["amc"],
            "intraday": lanes["intraday"],
        })

    return {"range": range_key, "as_of": as_of, "error": error, "days": days}


def reset_for_testing() -> None:
    """Test-only: force a clean in-memory cache without touching disk."""
    global _cache_rows, _cache_ts
    _cache_rows = None
    _cache_ts = 0.0
