"""One read of the TraderTV feed, as the Live Trader bot decides on it (ADR 055). Blocking: a worker thread.

The bot reads what the TraderTV LIVE page reads, through ``followed_traders``: the desk's day from the feed
(``feed.fetch_day``), each host's sighting on the bar (``routes.seen``: off air when another host's name tag has been
on the bar 60 s) with ``view.closed_on_leaving``, and the glued-ticker check (``routes.ticker_for`` over IBKR's
tape, advanced by ``exits.pump``). A trade's id is the page's (``view.trade_row``), and its ticker and prices the
ones the check settled on (``tickers.shown``). Nothing here sends an order. Shapes: ``decide``'s answer,
architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import logging
from typing import Any

from bot.live_trader import feed_rows

logger = logging.getLogger(__name__)


def down(state: str, error: str | None) -> dict[str, Any]:
    return {"state": state, "error": error, "date": None, "feed_now": None, "read_age_sec": None,
            "behind_sec": None, "live": False, "bar_visible": False, "order": [], "hosts": {}, "faces": []}


def read(now: float) -> dict[str, Any]:
    from followed_traders import config, exits, feed, routes, tickers, view

    base = config.feed_url()
    if base is None:
        return down("off", "NOVA_FOLLOW_FEED_URL is not set: there is no TraderTV feed to read")
    today = routes.desk_day(now)[0]
    try:
        day = feed.fetch_day(base, today)
    except feed.FeedError as exc:
        return down(exc.state, exc.message)
    day = {**day, "today": today}
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
    return {"state": "ok", "error": None, "date": day["date"], "feed_now": feed_rows.clock_ts(day["date"], clock),
            "read_age_sec": None if updated is None else round(max(0.0, now - updated), 1),
            "behind_sec": feed_rows.behind_sec(clock, updated), "live": bool((status or {}).get("live")),
            "bar_visible": bool((status or {}).get("bar_visible")), "order": list(hosts), "hosts": hosts,
            "faces": sorted(day.get("faces") or ())}


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
