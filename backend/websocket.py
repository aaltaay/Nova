"""
Alpaca trade WebSocket stream + in-memory cache overlays.

Owns: subscription state (``_ws_subscribed``, ``_ws_needs_resub``), trade
application to scanner caches, ticker-detail trade broadcast, and the
persistent reconnecting stream loop.

Extracted from ``main.py``. Cache mutations go through the typed runtime-state
owner so rebinding remains visible to every consumer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets

import hod_momo as _hod_momo
import hod_momo_universe as _hod_uni
from alpaca import _env, _get_discovery_provider, _get_feed, _try_fallback_to_iex
from cache import (
    save_afterhours_snapshot,
    save_gainer_snapshot,
    save_gapper_snapshot,
    save_loser_snapshot,
)
from constants import (
    ALPACA_WS_BACKOFF_CAP,
    ALPACA_WS_IDLE_POLL_SEC,
    HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK,
    SCANNER_MIN_PRICE,
)
from scanner import _gapper_meets_min_gap
from runtime_state import get_runtime_state
from ticker import _ticker_ws_clients

logger = logging.getLogger(__name__)

# ── Subscription state (owned here; mark_resub is the public mutator) ─────────
_ws_subscribed: set[str] = set()
_ws_needs_resub: bool = False


def alpaca_trades_drive_hod(provider: str | None = None) -> bool:
    """False when discovery=ibkr — IBKR ticks own HOD / tape ingest (single-feed)."""
    return (provider or _get_discovery_provider()) != "ibkr"


def mark_resub() -> None:
    """Signal the WebSocket loop to sync subscriptions on next iteration."""
    global _ws_needs_resub
    _ws_needs_resub = True


def current_symbols() -> set[str]:
    """Union of scanner caches, open ticker WS clients, and HOD Momo universe."""
    state = get_runtime_state()
    syms: set[str] = set()
    for g in state.gapper_cache:
        syms.add(g["symbol"])
    for g in state.afterhours_cache:
        syms.add(g["symbol"])
    for g in state.gainer_cache:
        syms.add(g["symbol"])
    for g in state.loser_cache:
        syms.add(g["symbol"])
    for sym, clients in _ticker_ws_clients.items():
        if clients:
            syms.add(sym)
    syms.update(state.hod_momo_universe)
    syms = {s for s in syms if not _hod_momo.is_blocked(s) or s in _ticker_ws_clients}
    return syms


def apply_trade_to_mover_list(cache: list[dict], sym: str, price: float, size: int = 0) -> bool:
    """Update price/change/volume for a symbol in a mover list; evict if below min price."""
    for i, g in enumerate(cache):
        if g["symbol"] == sym:
            if price < SCANNER_MIN_PRICE:
                del cache[i]
                return True
            prev_close = g.get("prev_close") or 0.0
            if prev_close:
                new_change_abs = price - prev_close
                new_change_pct = new_change_abs / prev_close
            else:
                new_change_abs = g.get("change_abs", 0)
                new_change_pct = g.get("change_pct", 0)
            cache[i] = {
                **g,
                "price": price,
                "change_abs": new_change_abs,
                "change_pct": new_change_pct,
                "volume": g.get("volume", 0) + size,
            }
            return True
    return False


def handle_trade(msg: dict) -> int | None:
    """Apply a real-time trade message to in-memory caches. Returns updated volume or None."""
    state = get_runtime_state()
    sym = msg.get("S")
    price = msg.get("p")
    if not sym or not price:
        return None
    size = int(msg.get("s") or 0)
    now = time.time()
    updated_volume: int | None = None

    # Alpaca WS must not overlay IBKR-sourced cache rows (single-feed rule).
    if _get_discovery_provider() == "ibkr":
        return None

    if state.current_mode == "premarket":
        for i, g in enumerate(state.gapper_cache):
            if g["symbol"] == sym:
                prev_close = g["previous_close"]
                new_gap = (price - prev_close) / prev_close if prev_close else g["gap_percent"]
                if price < SCANNER_MIN_PRICE or not _gapper_meets_min_gap(new_gap):
                    del state.gapper_cache[i]
                else:
                    new_vol = g.get("volume", 0) + size
                    state.gapper_cache[i] = {
                        **g,
                        "price": price,
                        "current_price": price,
                        "change_pct": new_gap,
                        "change_abs": price - prev_close,
                        "gap_percent": new_gap,
                        "volume": new_vol,
                    }
                    updated_volume = new_vol
                state.gapper_cache_ts = now
                save_gapper_snapshot(state.gapper_cache, state.gapper_cache_ts)
                break

    if state.current_mode == "afterhours":
        for i, g in enumerate(state.afterhours_cache):
            if g["symbol"] == sym:
                prev_close = g["previous_close"]
                new_gap = (price - prev_close) / prev_close if prev_close else g["gap_percent"]
                if price < SCANNER_MIN_PRICE or not _gapper_meets_min_gap(new_gap):
                    del state.afterhours_cache[i]
                else:
                    new_vol = g.get("volume", 0) + size
                    state.afterhours_cache[i] = {
                        **g,
                        "price": price,
                        "current_price": price,
                        "change_pct": new_gap,
                        "change_abs": price - prev_close,
                        "gap_percent": new_gap,
                        "volume": new_vol,
                    }
                    updated_volume = new_vol
                state.afterhours_cache_ts = now
                save_afterhours_snapshot(state.afterhours_cache, state.afterhours_cache_ts)
                break

    gainer_updated = apply_trade_to_mover_list(state.gainer_cache, sym, price, size)
    if gainer_updated:
        state.gainer_cache_ts = now
        if updated_volume is None:
            entry = next((g for g in state.gainer_cache if g["symbol"] == sym), None)
            if entry:
                updated_volume = entry.get("volume")

    loser_updated = apply_trade_to_mover_list(state.loser_cache, sym, price, size)
    if loser_updated:
        state.loser_cache_ts = now
        if updated_volume is None:
            entry = next((g for g in state.loser_cache if g["symbol"] == sym), None)
            if entry:
                updated_volume = entry.get("volume")

    # Independent revisions (ADR 008) — a Losers-only trade must never touch
    # Gainers' snapshot timestamp, and vice versa.
    if gainer_updated:
        save_gainer_snapshot(state.gainer_cache, now)
    if loser_updated:
        save_loser_snapshot(state.loser_cache, now)

    return updated_volume


async def broadcast_trade_update(
    sym: str,
    price: float,
    size: int | None,
    timestamp: str | None,
    volume: int | None = None,
    prev_close: float | None = None,
) -> None:
    """Push a lightweight trade update to ticker-detail WS clients watching this symbol."""
    clients = _ticker_ws_clients.get(sym)
    if not clients:
        return
    payload_obj: dict = {
        "type": "trade_update",
        "symbol": sym,
        "price": price,
        "size": size,
        "timestamp": timestamp,
        "volume": volume,
    }
    if prev_close is not None:
        payload_obj["prev_close"] = prev_close
    payload = json.dumps(payload_obj)
    dead: list = []
    for ws in list(clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def stream_loop() -> None:
    """Persistent Alpaca trade WebSocket with exponential backoff reconnect.

    When discovery=ibkr, do not open Alpaca's market-data socket at all — IBKR
    table/detail ticks own live prices and HOD. Poll until discovery flips back
    to alpaca (Settings / env) so we reclaim the single Alpaca WS slot.
    """
    global _ws_subscribed, _ws_needs_resub
    backoff = 1.0
    idle_logged = False

    while True:
        try:
            if not alpaca_trades_drive_hod():
                if _ws_subscribed:
                    _ws_subscribed = set()
                if not idle_logged:
                    logger.info(
                        "Alpaca WS idle — discovery=ibkr (IBKR owns live trades/HOD); "
                        "polling every %.0fs",
                        ALPACA_WS_IDLE_POLL_SEC,
                    )
                    idle_logged = True
                await asyncio.sleep(ALPACA_WS_IDLE_POLL_SEC)
                continue

            idle_logged = False

            api_key = _env("APCA_API_KEY_ID")
            api_secret = _env("APCA_API_SECRET_KEY")
            if not api_key or not api_secret:
                logger.warning("Alpaca WS: no API keys configured, sleeping 10s")
                await asyncio.sleep(10)
                continue

            feed = _get_feed()
            url = f"wss://stream.data.alpaca.markets/v2/{feed}"
            logger.info("Alpaca WS connecting to %s", url)

            async with websockets.connect(url, ping_interval=20, open_timeout=15) as ws:
                await ws.recv()
                await ws.send(json.dumps({"action": "auth", "key": api_key, "secret": api_secret}))
                auth_msgs = json.loads(await ws.recv())
                if not any(m.get("T") == "success" and m.get("msg") == "authenticated"
                           for m in auth_msgs):
                    is_sub_error = any(m.get("code") == 409 for m in auth_msgs)
                    if is_sub_error and _try_fallback_to_iex("WS auth 409 insufficient subscription"):
                        backoff = 1.0
                        continue
                    logger.warning("Alpaca WS auth failed (response: %s), retrying in %.1fs", auth_msgs, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, ALPACA_WS_BACKOFF_CAP)
                    continue

                logger.info("Alpaca WS authenticated")
                backoff = 1.0
                _ws_subscribed = set()
                _ws_needs_resub = True

                while True:
                    if not alpaca_trades_drive_hod():
                        logger.info("Alpaca WS closing — discovery switched to ibkr")
                        break

                    if _ws_needs_resub:
                        _ws_needs_resub = False
                        wanted = current_symbols()
                        to_add = wanted - _ws_subscribed
                        to_remove = _ws_subscribed - wanted
                        if to_add or to_remove:
                            logger.info(
                                "Alpaca WS subscribing +%d / -%d symbols (total %d)",
                                len(to_add), len(to_remove), len(wanted),
                            )
                        if to_add:
                            for chunk in _hod_uni.chunk_symbols(
                                to_add, HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK
                            ):
                                await ws.send(json.dumps({"action": "subscribe", "trades": chunk}))
                        if to_remove:
                            for chunk in _hod_uni.chunk_symbols(
                                to_remove, HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK
                            ):
                                await ws.send(json.dumps({"action": "unsubscribe", "trades": chunk}))
                        _ws_subscribed = wanted

                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msgs = json.loads(raw)
                        for msg in msgs:
                            if msg.get("T") == "t":
                                # discovery=ibkr: IBKR table/detail ticks own HOD + quote
                                # prices. Never feed Alpaca trades into on_trade_update /
                                # l2.tape (single-feed rule).
                                if not alpaca_trades_drive_hod():
                                    continue
                                updated_vol = handle_trade(msg)
                                sym = msg.get("S")
                                price = msg.get("p")
                                if sym and price:
                                    trade_ts = time.time()
                                    _hod_momo.on_trade_update(
                                        sym,
                                        float(price),
                                        trade_ts,
                                        volume=updated_vol,
                                    )
                                    try:
                                        from l2 import tape as _l2_tape
                                        _l2_tape.on_alpaca_trade(
                                            sym,
                                            float(price),
                                            float(msg.get("s") or 0),
                                            trade_ts,
                                            exchange=msg.get("x"),
                                        )
                                    except Exception:
                                        logger.exception("l2.tape: ingest failed for %s", sym)
                                if (
                                    sym and sym in _ticker_ws_clients and _ticker_ws_clients[sym]
                                ):
                                    asyncio.create_task(broadcast_trade_update(
                                        sym,
                                        msg.get("p"),
                                        msg.get("s"),
                                        msg.get("t"),
                                        updated_vol,
                                    ))
                    except asyncio.TimeoutError:
                        pass

        except asyncio.CancelledError:
            logger.info("Alpaca WS shutting down cleanly")
            raise
        except Exception as exc:
            if not alpaca_trades_drive_hod():
                await asyncio.sleep(ALPACA_WS_IDLE_POLL_SEC)
                continue
            logger.warning("Alpaca WS disconnected: %s, retrying in %.1fs", exc, backoff)
            _ws_subscribed = set()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, ALPACA_WS_BACKOFF_CAP)
