"""One read of the TraderTV feed, as the Live Trader bot decides on it (ADR 055). Blocking: a worker thread.

The bot reads what the TraderTV LIVE page reads, through ``followed_traders``: the desk's day from the feed
(``feed.fetch_day``), each host's sighting on the bar (``routes.seen``: off air when another host's name tag has been
on the bar 60 s) with ``view.closed_on_leaving``, and the glued-ticker check (``routes.ticker_for`` over IBKR's
tape, advanced by ``exits.pump``). A trade's id is the page's (``view.trade_row``), and its ticker and prices the
ones the check settled on (``tickers.shown``). For the bad-read rules (bot.md, "Bad reads") each host carries the
sides its reads could not read whole (``unread``, from the page's read log) and the answer carries every trade of
the feed's previous day as ``previous`` (side, stock, average), read once a day. An answer that cannot be folded
is a feed that is not answering (``bad_answer``), never a failed pass. Nothing here sends an order. Shapes:
``decide``'s answer, architecture/schema/bot.md ("The Live Trader bot"). Owner of ``_previous``: this module, in
process memory (one day's keys; schema_version n/a).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.live_trader import feed_rows
from bot.live_trader.constants_live_trader import LT_PREVIOUS_RETRY_SEC

logger = logging.getLogger(__name__)
_previous: dict[str, Any] = {"date": None, "keys": [], "retry_ts": None}


def reset_for_tests() -> None:
    _previous.update(date=None, keys=[], retry_ts=None)


def down(state: str, error: str | None) -> dict[str, Any]:
    return {"state": state, "error": error, "date": None, "feed_now": None, "read_age_sec": None,
            "behind_sec": None, "live": False, "bar_visible": False, "order": [], "hosts": {}, "faces": []}


def read(now: float) -> dict[str, Any]:
    from followed_traders import config, feed, routes

    base = config.feed_url()
    if base is None:
        return down("off", "NOVA_FOLLOW_FEED_URL is not set: there is no TraderTV feed to read")
    today = routes.desk_day(now)[0]
    try:
        day = feed.fetch_day(base, today)
    except feed.FeedError as exc:
        return down(exc.state, exc.message)
    try:
        return _fold(base, {**day, "today": today}, now)
    except Exception as exc:
        logger.exception("Live Trader bot: the feed's answer could not be folded")
        return down("bad_answer", f"the feed's answer could not be read ({type(exc).__name__}: {exc})")


def _fold(base: str, day: dict[str, Any], now: float) -> dict[str, Any]:
    from followed_traders import exits, routes, tickers, view

    status = day.get("status")
    seen = routes.seen(base, day, now)
    ready = routes.ibkr_ready()
    ticker_for = routes.ticker_for(now, ready)
    bars = _bars(status)
    hosts: dict[str, dict[str, Any]] = {}
    for t in day["trades"]:
        gone = view.left_bar(seen, t["trader"])
        trade = view.closed_on_leaving(t, gone)
        host = hosts.setdefault(t["trader"], {"left_ts": gone["left_ts"] if gone else None, "rows": []})
        host["rows"].append(_row(trade, ticker_for, tickers, bars))
    on_bar = [*((status or {}).get("traders") or []), *(h["trader"] for h in (status or {}).get("positions") or [])]
    for name in on_bar:                      # a host on the bar with nothing open is watched too
        if name not in hosts:
            gone = view.left_bar(seen, name)
            hosts[name] = {"left_ts": gone["left_ts"] if gone else None, "rows": []}
    exits.pump(now, ibkr_ready=ready)
    updated = (status or {}).get("updated_at")
    clock = (status or {}).get("clock")
    feed_now = feed_rows.clock_ts(day["date"], clock)
    unread = feed_rows.unread_sides(routes.read_log(base, day["date"], now), day["date"], feed_now)
    for name, host in hosts.items():
        host["unread"] = sorted(unread.get(name, ()))
    return {"state": "ok", "error": None, "date": day["date"], "feed_now": feed_now,
            "read_age_sec": None if updated is None else round(max(0.0, now - updated), 1),
            "behind_sec": feed_rows.behind_sec(clock, updated), "live": bool((status or {}).get("live")),
            "bar_visible": bool((status or {}).get("bar_visible")), "order": list(hosts), "hosts": hosts,
            "faces": sorted(day.get("faces") or ()), "previous": _previous_keys(base, day, now)}


def _previous_keys(base: str, day: dict[str, Any], now: float) -> list[list[Any]]:
    """Every trade of the feed's day before ``day`` as ``[side, symbol, average]`` (each average it showed, to the
    cent), read once a day: a bar still showing an earlier show's rows is never taken for new positions."""
    from followed_traders import feed

    prev = next((d for d in day.get("dates") or () if d < day["date"]), None)
    if prev is None:
        return []
    if _previous["date"] == prev and (_previous["retry_ts"] is None or now < _previous["retry_ts"]):
        return _previous["keys"]
    try:
        got = feed.fetch_day(base, prev)
    except feed.FeedError as exc:
        logger.warning("Live Trader bot: the feed's %s could not be read (%s): asked again in %.0f s", prev,
                       exc.message, LT_PREVIOUS_RETRY_SEC)
        _previous.update(date=prev, keys=[], retry_ts=now + LT_PREVIOUS_RETRY_SEC)
        return []
    keys = sorted({(t["side"], t["symbol"], p) for t in got["trades"] for p in feed_rows.averages(t)})
    _previous.update(date=prev, keys=[list(k) for k in keys], retry_ts=None)
    return _previous["keys"]


def _bars(status: dict[str, Any] | None) -> dict[str, set[str]] | None:
    """Each host's bar as the feed last confirmed it, ``{host: {"side:SYMBOL"}}``; None when the feed sends none."""
    held = (status or {}).get("positions")
    if held is None:
        return None
    return {h["trader"]: {f"{p['side']}:{p['symbol']}" for p in h["positions"]} for h in held}


def _row(t: dict[str, Any], ticker_for: Any, tickers: Any, bars: dict[str, set[str]] | None) -> dict[str, Any]:
    """A trade as ``decide`` reads it: the page's id, the ticker and prices as the check settled them, and whether
    the host's bar shows it now (``on_bar``: None when the feed sends no bar)."""
    row_id = f"{t['trader']}|{t['side']}|{t.get('read_as') or t['symbol']}|{t['entry_ts']:.0f}"
    on_bar = None if bars is None else f"{t['side']}:{t['symbol']}" in bars.get(t["trader"], set())
    ticker = ticker_for(t) if t["status"] == "open" else None
    shown = tickers.shown(t, ticker)
    return {"id": row_id, "host": t["trader"], "side": t["side"], "symbol": shown["symbol"], "status": t["status"],
            "price": shown["price"], "entry_price": shown["entry_price"], "entry_ts": t["entry_ts"],
            "known": bool(t["entry_known"]), "adds": [dict(a) for a in shown["adds"]], "exit_ts": t.get("exit_ts"),
            "left_bar": bool(t.get("left_bar")), "on_bar": on_bar,
            "ticker": None if ticker is None else {"state": ticker["state"], "why": ticker.get("why")}}
