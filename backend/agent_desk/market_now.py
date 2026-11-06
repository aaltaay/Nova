"""``GET /api/agent/market-now``: today's market in one answer, from what the Market and Global pages already hold.

Asking marks both pages wanted, so their readers run; nothing here waits on IBKR. Whatever has no answer is named in
``missing`` -- an agent says so, and never fills the hole from elsewhere. Read-only: nothing here places anything.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SOURCE_RULE = "Prices are IBKR's. Headlines are Alpaca's, kept by Nova. Percentages are percent points."
_PARAMS = {"sectors": "1D", "industries": "1D", "climate": "1D", "top": "biggest", "top_period": "1D"}


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    return bool(is_replay_desk())


def _market(now: float, replay: bool) -> dict[str, Any]:
    from market_board import board, refresh
    from market_board.state import store

    on = refresh.enabled()
    if on:
        refresh.want(now)
    return board.compose(store(), now, enabled=on, replay_desk=replay, params=_PARAMS)


def _global(now: float, replay: bool) -> dict[str, Any]:
    from global_board import board, reads, refresh
    from global_board.state import store

    on = refresh.enabled()
    if on:
        refresh.want("1D", now)
    return board.compose(store(), now, enabled=on, replay_desk=replay, period="1D",
                         history_left=reads.history_left(), history_headroom=reads.headroom(now))


def _quote(q: Mapping) -> dict[str, Any]:
    return {k: q.get(k) for k in ("id", "label", "last", "change_pct", "at", "stale", "error")}


def _missing(market: Mapping, world: Mapping, news: Mapping) -> list[str]:
    out = [f"{q['label']}: {q.get('error') or 'no price yet'}" for q in market["quotes"] if q.get("change_pct") is None]
    out += [f"{g['label']}: {g['total'] - g['priced']} of {g['total']} stocks not priced yet"
            for g in market["themes"]["groups"] if g["priced"] < g["total"]]
    out += [f"{m['name']} money: {m['flow']['error']}" for m in world["markets"] if m["flow"].get("pressure_pct") is None]
    if news.get("error"):
        out.append(f"headlines: {news['error']}")
    return out


def report(words: str | None, limit: int, now: float) -> dict[str, Any]:
    from market_news import feed

    replay = _replay_desk()
    market, world = _market(now, replay), _global(now, replay)
    wanted = [w.strip() for w in (words or "").split(",") if w.strip()]
    news = feed.read(wanted, limit, now)
    return {
        "as_of": now, "replay_desk": replay, "session": market["session"], "day_read": market["day_read"],
        "quotes": [_quote(q) for q in market["quotes"]], "breadth": market["breadth"],
        "sectors": market["sectors"], "top": market["top"], "themes": market["themes"],
        "world": {"read": world["read"], "totals": world["world"], "regions": world["regions"]},
        "headlines": news, "missing": _missing(market, world, news), "rule": SOURCE_RULE,
    }
