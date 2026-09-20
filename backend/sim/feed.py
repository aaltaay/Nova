"""Sim Feed loop -- steps SIM1 tape and injects T&S / L2 / quote updates."""
from __future__ import annotations

import asyncio
import logging

from constants_sim import SIM_PRINT_SIZE, SIM_SYMBOL
from sim import broker as _broker
from sim import market as _market
from sim import session_clock as _clock

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def reset_for_tests() -> None:
    stop_sim_feed()


def start_sim_feed() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.get_running_loop().create_task(_run(), name="sim-feed")
    logger.info("SIM: feed started symbol=%s", SIM_SYMBOL)


def stop_sim_feed() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    _task = None
    logger.info("SIM: feed stopped")


def start_sim_feed_threadsafe() -> None:
    """Start feed on the FastAPI HTTP loop even when called from a worker thread."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        start_sim_feed()
        return
    try:
        from ibkr.loop_supervisor import get_http_loop

        http = get_http_loop()
    except Exception:
        http = None
    if http is not None and http.is_running():
        http.call_soon_threadsafe(start_sim_feed)
        logger.info("SIM: feed scheduled on http loop")
        return
    logger.warning("SIM: feed start skipped — no running asyncio loop")


def stop_sim_feed_threadsafe() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        stop_sim_feed()
        return
    try:
        from ibkr.loop_supervisor import get_http_loop

        http = get_http_loop()
    except Exception:
        http = None
    if http is not None and http.is_running():
        http.call_soon_threadsafe(stop_sim_feed)
        return
    stop_sim_feed()


async def _run() -> None:
    while True:
        try:
            tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("SIM: feed tick failed")
        await asyncio.sleep(_clock.phase_tick_interval_sec())


def tick() -> dict:
    """One synchronous tape step + fill match + fan-out. Used by tests."""
    if _clock.is_paused():
        return {}
    from sim import history_playback
    if history_playback.status():
        return {}  # Historical snapshots own tape/quotes; never inject SIM1 here.
    from sim import replay as _replay
    if not _replay.status_payload()["replay_ok"]:
        return {}  # Failed selection must be acknowledged by selecting a source.
    if _replay.is_capture_replay():
        try:
            return _capture_tick()
        except Exception:
            logger.exception("SIM: capture play tick failed")
            _replay.fail_replay("Capture playback failed; select a recording or return to SIM1")
            return {}
    payload = _market.step()
    _broker.try_fill_working(_market.last())
    _inject(payload)
    return payload


def _capture_tick() -> dict:
    """Forward recorded events only; quiet intervals are not trades."""
    from datetime import datetime, timezone
    from sim import capture_player as player
    from sim import replay
    from ibkr.tape_stream import _push_queue
    from ibkr.depth import state as depth_state

    now_ts = _clock.now_et().timestamp()
    symbol = replay.status_payload()["replay_symbol"]
    rows = player.prints_since(player.last_emit_ts(), now_ts)
    last_payload: dict = {}
    for row in rows[-20:]:  # Preserve the existing bounded scrub burst policy.
        ts = float(row["ts"])
        payload = {
            "type": "print", "symbol": symbol,
            "time": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "price": float(row["price"]), "size": int(row.get("size") or 0),
            "exchange": str(row.get("exchange") or ""),
            "conditions": str(row.get("conditions") or ""),
            "side": row.get("side"), "bid": row.get("bid"), "ask": row.get("ask"),
        }
        _push_queue(symbol, payload)
        _broadcast_capture(payload)
        player.mark_emitted(ts)
        last_payload = payload
    book = player.book_at()
    if book is not None:
        depth_state.push_book(symbol, {**book, "symbol": symbol})
    return last_payload


def _broadcast_capture(payload: dict) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def broadcast() -> None:
        try:
            from websocket import broadcast_trade_update
            await broadcast_trade_update(
                payload["symbol"], payload["price"], payload["size"], payload["time"],
                None, None,
            )
        except Exception:
            logger.warning("SIM: captured trade broadcast failed", exc_info=True)

    loop.create_task(broadcast())


def _inject(payload: dict) -> None:
    try:
        from capture.bridge_sim import emit_sim_tick

        emit_sim_tick(payload, _market.quote() or {}, _market.book())
    except Exception:
        # D-068: this used to be logger.debug, and root is INFO — a failing
        # capture bridge produced no line anywhere while the session was lost.
        logger.warning("SIM: capture bridge failed", exc_info=True)

    try:
        from ibkr.tape_stream import _push_queue

        _push_queue(SIM_SYMBOL, payload)
    except Exception:
        logger.debug("SIM: tape inject skipped", exc_info=True)

    try:
        from ibkr.depth import state as _depth_state

        book = dict(_market.book())
        book["symbol"] = SIM_SYMBOL
        _depth_state.push_book(SIM_SYMBOL, book)
    except Exception:
        logger.debug("SIM: depth inject skipped", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    q = _market.quote() or {}
    last = q.get("last")
    if last is None:
        return

    async def _broadcast() -> None:
        try:
            from websocket import broadcast_trade_update

            await broadcast_trade_update(
                SIM_SYMBOL,
                float(last),
                int(payload.get("size") or SIM_PRINT_SIZE),
                payload.get("time"),
                q.get("volume"),
                q.get("prev_close"),
            )
        except Exception:
            logger.debug("SIM: quote inject skipped", exc_info=True)

    loop.create_task(_broadcast())
