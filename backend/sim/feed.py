"""Sim Feed loop -- streams a recorded capture and matches practice orders.

There is no synthetic tape. With nothing loaded the loop is idle; a historical
window serves its own snapshots, so the loop only matches practice orders
against its prints (architecture/practice-fills.md).
"""
from __future__ import annotations

from capture.constants_capture import CAPTURE_FEED_EMIT_LIMIT

import asyncio
import logging

from sim import broker as _broker
from sim import practice
from sim import session_clock as _clock

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
# (replay key, playhead ts) of the last fill match; practice orders only ever
# fill on prints after it, so a backward scrub or a new replay never back-fills.
_fill_cursor: tuple[tuple, float] | None = None


def reset_for_tests() -> None:
    global _fill_cursor
    stop_sim_feed()
    _fill_cursor = None


def start_sim_feed() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.get_running_loop().create_task(_run(), name="sim-feed")
    logger.info("SIM: feed started")


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
    """One synchronous capture step + practice fill match. Used by tests."""
    if _clock.is_paused():
        return {}
    from sim import history_playback
    from sim import replay as _replay
    payload: dict = {}
    if not history_playback.status():
        # A failed selection must be acknowledged by selecting a source; a
        # loading one (``replay_ok`` null) has nothing to tick yet.
        if not _replay.status_payload()["replay_ok"]:
            return {}
        # At the live edge the live feed owns the panels (ADR 020 live-edge
        # amendment): today's recording stays loaded for the scrub back, but
        # its prints are not forwarded on top of the live tape.
        if _replay.is_capture_replay() and not _clock.live_edge():
            try:
                payload = _capture_tick()
            except Exception:
                logger.exception("SIM: capture play tick failed")
                _replay.fail_replay("Capture playback failed; select a recording or a historical window")
                return {}
    match_practice_fills()
    expire_practice_orders()
    return payload


def expire_practice_orders() -> list[dict]:
    """Expire DAY practice orders once the playhead reaches the replayed session's close.

    Runs after the fill match so a print at the close itself still fills and a
    print past it never does (``practice.order_rules``). The expiry event is
    stamped at the close, so a scrub back before it restores the order.
    """
    if practice.loaded() is None:
        return []
    return _broker.expire_due(practice.playhead_ts())


def match_practice_fills() -> list[dict]:
    """Fill resting practice orders on the replay prints since the last match."""
    global _fill_cursor
    active = practice.loaded()
    now = practice.playhead_ts()
    if active is None:
        _fill_cursor = None
        return []
    previous = _fill_cursor
    _fill_cursor = (active.key, now)
    if previous is None or previous[0] != active.key or now <= previous[1]:
        return []
    prints = practice.prints_between(active.symbol, previous[1], now)
    return _broker.try_fill_working(active.symbol, prints) if prints else []


def rewind_fill_cursor(ts: float) -> None:
    """The account was unwound to ``ts``: the next match re-plays the tape from there.

    Without this the cursor would still sit where the last match left it and
    skip the stretch the operator is replaying. Lock-free (the cursor's own key
    is kept; a stale key re-anchors on the next match as it always did).
    """
    global _fill_cursor
    if _fill_cursor is not None and _fill_cursor[1] > float(ts):
        _fill_cursor = (_fill_cursor[0], float(ts))


def reset_fill_cursor() -> None:
    """The account started over: the next match anchors afresh on what is loaded."""
    global _fill_cursor
    _fill_cursor = None


def _capture_tick() -> dict:
    """Forward recorded events only; quiet intervals are not trades."""
    from datetime import datetime, timezone
    from sim import capture_player as player
    from ibkr.tape_stream import _push_queue
    from ibkr.depth import state as depth_state

    now_ts = _clock.now_et().timestamp()
    selection = player.snapshot()
    if selection is None:
        return {}
    symbol = selection.symbol
    rows = player.prints_since(selection.last_emit, now_ts, state=selection)
    last_payload: dict = {}
    for row in rows[-CAPTURE_FEED_EMIT_LIMIT:]:  # Preserve the existing bounded scrub burst policy.
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
        player.mark_emitted(ts, state=selection)
        last_payload = payload
    book = player.book_at(state=selection)
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

