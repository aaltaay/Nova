"""
Ticker detail routes — thin FastAPI router delegating to backend/ticker.py.

Endpoints:
  GET  /api/ticker/{symbol}        -- full ticker detail (asset + snapshot + news + funds)
  GET  /api/ticker/{symbol}/bars   -- OHLCV chart bars (IBKR or Alpaca per discovery)
  WS   /ws/ticker/{symbol}         -- two-phase streaming detail + live trade updates
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from alpaca import _alpaca_headers, _env, _get_discovery_provider, _get_feed
from constants import CHART_DEFAULT_BARS, CHART_DEFAULT_TIMEFRAME
from ibkr import ticks as _ibkr_ticks
from websocket import mark_resub

router = APIRouter(tags=["ticker"])
logger = logging.getLogger(__name__)


@router.get("/api/ticker/{symbol}")
def get_ticker_detail(symbol: str):
    """Fetch full detail for a single symbol: asset info, snapshot, news, avg volume."""
    from ticker import _build_ticker_detail
    return _build_ticker_detail(symbol.upper())


@router.get("/api/ticker/{symbol}/bars")
def get_ticker_bars(
    symbol: str,
    timeframe: str = CHART_DEFAULT_TIMEFRAME,
    limit: int = CHART_DEFAULT_BARS,
):
    """Fetch OHLCV bars for a symbol (IBKR when discovery=ibkr, else Alpaca)."""
    from chart_bars import fetch_chart_bars
    return fetch_chart_bars(
        symbol.upper(),
        timeframe,
        limit,
        discovery_provider=_get_discovery_provider(),
        interactive=True,
    )


@router.websocket("/ws/ticker/{symbol}")
async def ws_ticker_detail(websocket: WebSocket, symbol: str):
    """WebSocket endpoint: sends full detail on connect, then streams real-time trade updates.

    Two-phase send for perceived speed:
      1. 'initial' — fast data (asset + snapshot + cached avg volume) sent first (~300 ms).
      2. 'detail_update' — slow data (news + fresh avg volume + fundamentals) sent when ready.
    """
    import ticker as _ticker_mod

    symbol = symbol.upper()
    await websocket.accept()

    _ticker_mod._ticker_ws_clients.setdefault(symbol, set()).add(websocket)
    mark_resub()
    if _get_discovery_provider() == "ibkr":
        asyncio.create_task(_ibkr_ticks.subscribe(symbol))

    loop = asyncio.get_event_loop()
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()

    try:
        if not headers:
            await websocket.send_text(json.dumps({"type": "initial", "error": "API keys not configured"}))
        else:
            feed = _get_feed()

            fast_task = loop.run_in_executor(
                None, lambda: _ticker_mod._build_ticker_fast(symbol, base_url, headers, feed)
            )
            slow_task = loop.run_in_executor(
                None, lambda: _ticker_mod._build_ticker_slow(symbol, headers)
            )

            fast = await fast_task
            await websocket.send_text(json.dumps({"type": "initial", **fast}))

            slow = await slow_task
            avg_vol = slow.get("avg_volume")
            daily_vol = (fast.get("snapshot", {}).get("daily_bar") or {}).get("volume") or 0
            rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else fast.get("rel_volume")
            from listing_compare import build_listing_compare
            from news.enrich import build_ticker_news_impact
            news_impact = build_ticker_news_impact(
                symbol, slow.get("news") or [], fast.get("snapshot"), rel_vol
            )
            listing = await loop.run_in_executor(
                None, lambda: build_listing_compare(symbol, fast.get("asset") or {})
            )
            await websocket.send_text(json.dumps({
                "type": "detail_update",
                "news": slow["news"],
                "fundamentals": slow["fundamentals"],
                "avg_volume": avg_vol,
                "rel_volume": rel_vol,
                "rvol_5min": fast.get("rvol_5min"),
                "volume_in_5min": fast.get("volume_in_5min"),
                "news_impact": news_impact,
                "listing": listing,
            }))

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.debug("Ticker WS client disconnected for %s", symbol)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Ticker WS loop failed for %s", symbol)
    finally:
        import ticker as _ticker_mod2
        _ticker_mod2._ticker_ws_clients.get(symbol, set()).discard(websocket)
        if not _ticker_mod2._ticker_ws_clients.get(symbol):
            _ticker_mod2._ticker_ws_clients.pop(symbol, None)
            if _get_discovery_provider() == "ibkr":
                asyncio.create_task(_ibkr_ticks.unsubscribe(symbol))
        mark_resub()
