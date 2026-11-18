"""The running desk's IBKR candles, for a review day the Massive files do not hold.

Owner: this module. The files end where the download ended and never hold today, so the review route asks
the desk for those days: ``GET /api/ticker/{symbol}/bars``, the candles the desk's own charts paint (IBKR
history, store-first, ADR 012). Read only: nothing is written, and a day the desk does not hold is refused
with the reason, never drawn from something else.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote, urlencode
from urllib.request import urlopen

import nova_review_causal as causal

DEFAULT_API = "http://127.0.0.1:8000"
ORIGIN = "desk-ibkr"
DESK_SOURCE = "ibkr"                     # what the desk's bars route names for IBKR candles; a Sim replay names another
DESK_TF = {"10s": "10Sec", "1m": "1Min", "5m": "5Min"}
DESK_DAILY_TF = "1Day"
DESK_LIMIT = 5000                        # the desk's own ceiling (CHART_MAX_BARS)
HTTP_TIMEOUT_SEC = 10.0
FILL_WAIT_SEC = 12.0                     # a stock the desk has not opened answers empty first, then fills
FILL_POLL_SEC = 1.0


class DeskUnavailable(LookupError):
    """The desk could not give IBKR candles for the day. The message is the reason the page shows."""


def api_base() -> str:
    return (os.environ.get("NOVA_API_BASE") or DEFAULT_API).rstrip("/")


def _http_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=HTTP_TIMEOUT_SEC) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = str(json.loads(exc.read().decode()).get("detail") or "")
        except (ValueError, AttributeError, OSError):
            detail = ""
        raise DeskUnavailable(f"the desk answered HTTP {exc.code}" + (f": {detail}" if detail else "")) from exc
    except OSError as exc:
        raise DeskUnavailable(f"the desk did not answer at {api_base()} ({exc})") from exc
    try:
        body = json.loads(raw.decode())
    except ValueError as exc:
        raise DeskUnavailable("the desk's answer was not JSON") from exc
    if not isinstance(body, dict):
        raise DeskUnavailable("the desk's answer was not a bars payload")
    return body


# A test swaps these; the wait is injectable so no test sleeps.
fetch_json: Callable[[str], dict[str, Any]] = _http_json
sleep: Callable[[float], None] = time.sleep


def _waiting_on_ibkr(body: dict[str, Any]) -> bool:
    coverage = body.get("coverage") or {}
    return bool(coverage.get("filling") or coverage.get("history_pending"))


def _start_et(bar: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(bar["t"]).replace("Z", "+00:00")).astimezone(causal.ET)


def _holds_day(bars: list[dict[str, Any]], day: str | None) -> bool:
    if day is None:
        return bool(bars)
    return any(_start_et(bar).date().isoformat() == day for bar in bars)


def desk_series(symbol: str, timeframe: str, day: str | None = None) -> list[dict[str, Any]]:
    """The desk's whole stored series for one timeframe.

    A stock the desk has not opened today answers with nothing, or with an earlier day's bars, while its
    fill is queued: this asks again until the series holds ``day`` (any bar when ``day`` is None), the desk
    stops filling, or ``FILL_WAIT_SEC`` has passed.
    """
    query = urlencode({"timeframe": timeframe, "limit": DESK_LIMIT})
    url = f"{api_base()}/api/ticker/{quote(symbol)}/bars?{query}"
    waited = 0.0
    while True:
        body = fetch_json(url)
        source = body.get("source")
        if source != DESK_SOURCE:
            raise DeskUnavailable(
                f"the desk is not showing IBKR's live history (its bars are {source or 'unnamed'}; a Sim replay?)")
        bars = list(body.get("bars") or [])
        if _holds_day(bars, day) or not _waiting_on_ibkr(body) or waited >= FILL_WAIT_SEC:
            last_error = (body.get("coverage") or {}).get("last_error")
            if not bars and last_error:
                raise DeskUnavailable(f"IBKR did not answer the desk: {last_error}")
            return bars
        sleep(FILL_POLL_SEC)
        waited += FILL_POLL_SEC


def _row(bar: dict[str, Any]) -> dict[str, Any]:
    return {"open": bar.get("o"), "high": bar.get("h"), "low": bar.get("l"), "close": bar.get("c"),
            "volume": bar.get("v")}


def desk_bars(symbol: str, day: str, tf: str) -> list[dict[str, Any]]:
    """The asked Eastern day's bars, in the front door's row shape (``time_et``, ``open`` ... ``volume``)."""
    rows = []
    # Only the 1-minute read waits for the day: it decides whether the page exists at all.
    for bar in desk_series(symbol, DESK_TF[tf], day if tf == "1m" else None):
        start = _start_et(bar)
        if start.date().isoformat() == day:
            rows.append({"time_et": start, **_row(bar)})
    if tf == "1m" and not rows:
        raise DeskUnavailable(f"the desk holds no IBKR 1-minute candle of {symbol} on {day}")
    return rows


def desk_daily(symbol: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
    """Daily rows ``date_from`` to ``date_to``. IBKR's daily stamp is the session date itself, so it is not shifted."""
    rows = []
    for bar in desk_series(symbol, DESK_DAILY_TF):
        key = str(bar["t"])[:10]
        if date_from <= key <= date_to:
            rows.append({"date": key, **_row(bar)})
    return rows


desk_bars.origin = ORIGIN  # type: ignore[attr-defined]
desk_bars.sources = {tf: "ibkr-history" for tf in DESK_TF}  # type: ignore[attr-defined]
desk_daily.source = "ibkr-daily"  # type: ignore[attr-defined]

READERS = (desk_bars, desk_daily)
