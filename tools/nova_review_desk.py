"""The running desk's IBKR candles, for a review day the Massive files do not hold.

Owner: this module. The files end where the download ended and never hold today, so the review route asks
the desk for those days: ``GET /api/ticker/{symbol}/bars``, the candles the desk's own charts paint (IBKR
history, store-first, ADR 012). Read only: nothing is written, and a day the desk does not hold is refused
with the reason, never drawn from something else.
"""
from __future__ import annotations

import json
import os
import threading
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
HTTP_TIMEOUT_SEC = 5.0                   # a loopback store read; long enough, and short beside the page's wait
FILL_WAIT_SEC = 12.0                     # one wait per page, shared by its four reads; under the screenshot's 25 s
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


# A test swaps these; the wait and the clock are injectable so no test sleeps.
fetch_json: Callable[[str], dict[str, Any]] = _http_json
sleep: Callable[[float], None] = time.sleep
clock: Callable[[], float] = time.monotonic

# One page, one wait. ``load_review`` reads minutes, dailies, 5-minute and 10-second bars in turn; a wait
# per read (4 x 12 s on a stock the desk never opened) outlasted the screenshot's 25 s. The 1-minute read
# opens the symbol's budget and asks for every timeframe at once, so the desk fills them side by side and
# the later reads spend what is left of the same 12 s.
_budgets: dict[str, float] = {}
_budget_lock = threading.Lock()


def _open_budget(symbol: str) -> float:
    deadline = clock() + FILL_WAIT_SEC
    with _budget_lock:
        _budgets[symbol] = deadline
    return deadline


def _budget(symbol: str) -> float:
    """The page's deadline for ``symbol``. Unset or already past means one ask and no wait."""
    with _budget_lock:
        return _budgets.get(symbol, 0.0)


def _bars_url(symbol: str, timeframe: str) -> str:
    query = urlencode({"timeframe": timeframe, "limit": DESK_LIMIT})
    return f"{api_base()}/api/ticker/{quote(symbol)}/bars?{query}"


def _prime(symbol: str, timeframes: tuple[str, ...]) -> None:
    """Ask once for each timeframe so the desk queues their fills now. The answers are read later."""
    for timeframe in timeframes:
        try:
            fetch_json(_bars_url(symbol, timeframe))
        except DeskUnavailable:
            return      # the read that follows meets the same desk and raises the reason


def _start_et(bar: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(bar["t"]).replace("Z", "+00:00")).astimezone(causal.ET)


def _holds_day(bars: list[dict[str, Any]], day: str | None) -> bool:
    if day is None:
        return bool(bars)
    return any(_start_et(bar).date().isoformat() == day for bar in bars)


def read_series(symbol: str, timeframe: str, day: str | None, deadline: float) -> tuple[list[dict[str, Any]], bool]:
    """The desk's stored series for one timeframe, and whether IBKR's history was still owed at the end.

    ``history_pending`` is the desk saying the rows it holds are not IBKR's history yet: nothing, an earlier
    session's bars, or only the few minutes its live tape has built (``bars_store.history_pending``). Those
    are never taken as the day: this asks again until history has landed and the series holds ``day`` (any
    bar when ``day`` is None), the desk stops filling, or ``deadline`` passes. A series still pending at the
    deadline comes back flagged, for the caller to refuse.
    """
    url = _bars_url(symbol, timeframe)
    while True:
        body = fetch_json(url)
        source = body.get("source")
        if source != DESK_SOURCE:
            raise DeskUnavailable(
                f"the desk is not showing IBKR's live history (its bars are {source or 'unnamed'}; a Sim replay?)")
        bars = list(body.get("bars") or [])
        coverage = body.get("coverage") or {}
        pending = bool(coverage.get("history_pending"))
        settled = not pending and (_holds_day(bars, day) or not coverage.get("filling"))
        if settled or clock() >= deadline:
            last_error = coverage.get("last_error")
            if (pending or not bars) and last_error:
                raise DeskUnavailable(f"IBKR did not answer the desk: {last_error}")
            return bars, pending
        sleep(FILL_POLL_SEC)


def desk_series(symbol: str, timeframe: str, day: str | None = None) -> list[dict[str, Any]]:
    """One timeframe's series with its own ``FILL_WAIT_SEC``; refused while IBKR's history is still owed."""
    bars, pending = read_series(symbol, timeframe, day, clock() + FILL_WAIT_SEC)
    if pending:
        raise DeskUnavailable(f"IBKR's {timeframe} history of {symbol} has not reached the desk yet")
    return bars


def _row(bar: dict[str, Any]) -> dict[str, Any]:
    return {"open": bar.get("o"), "high": bar.get("h"), "low": bar.get("l"), "close": bar.get("c"),
            "volume": bar.get("v")}


def desk_bars(symbol: str, day: str, tf: str) -> list[dict[str, Any]]:
    """The asked Eastern day's bars, in the front door's row shape (``time_et``, ``open`` ... ``volume``)."""
    minutes = tf == "1m"
    if minutes:
        # The page's first read: it opens the shared wait and decides whether the page exists at all.
        deadline = _open_budget(symbol)
        _prime(symbol, tuple(name for name in (*DESK_TF.values(), DESK_DAILY_TF) if name != DESK_TF["1m"]))
    else:
        deadline = _budget(symbol)
    bars, pending = read_series(symbol, DESK_TF[tf], day if minutes else None, deadline)
    if pending:
        if minutes:
            raise DeskUnavailable(f"IBKR's 1-minute history of {symbol} has not reached the desk yet; ask again shortly")
        return []       # an empty pane, never the live tape's few bars passed off as the session
    rows = []
    for bar in bars:
        start = _start_et(bar)
        if start.date().isoformat() == day:
            rows.append({"time_et": start, **_row(bar)})
    if minutes and not rows:
        raise DeskUnavailable(f"the desk holds no IBKR 1-minute candle of {symbol} on {day}")
    return rows


def desk_daily(symbol: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
    """Daily rows ``date_from`` to ``date_to``. IBKR's daily stamp is the session date itself, so it is not shifted."""
    bars, pending = read_series(symbol, DESK_DAILY_TF, None, _budget(symbol))
    if pending:
        return []       # no prior-day levels rather than ones from an unfinished series
    rows = []
    for bar in bars:
        key = str(bar["t"])[:10]
        if date_from <= key <= date_to:
            rows.append({"date": key, **_row(bar)})
    return rows


desk_bars.origin = ORIGIN  # type: ignore[attr-defined]
desk_bars.sources = {tf: "ibkr-history" for tf in DESK_TF}  # type: ignore[attr-defined]
desk_daily.source = "ibkr-daily"  # type: ignore[attr-defined]

READERS = (desk_bars, desk_daily)
