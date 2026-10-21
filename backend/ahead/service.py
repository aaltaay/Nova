"""What ``GET /api/ahead/forecast/{symbol}`` and ``/api/ahead/status`` answer (ADR 061). The route never waits on the
forecaster: it answers ``pending`` while an ask runs on the forecaster's own threads, and the next poll reads it.

The gates, in order, each answering its own state with no forecast numbers:

1. no completed candles -> ``not_enough_bars`` (``have`` 0, no ``as_of``);
2. no forecaster set up -> ``not_set_up``, and no request leaves Nova;
3. a candle ending after the desk clock -> ``error`` (fails closed: nothing is sent);
4. fewer than ``AHEAD_MIN_BARS`` candles -> ``not_enough_bars`` (the forecaster is not asked);
5. the newest candle more than ``AHEAD_MAX_TAIL_GAP_SEC`` behind the desk minute -> ``quiet``;
6. ``AHEAD_BREAKER_FAILS`` asks in a row with no answer -> ``offline`` until ``retry_at`` (wall clock: the breaker
   counts real seconds, so on a paused or scrubbed replay the playhead never says when it reopens).

Then the memory: a forecast is kept per ``(symbol, as_of, venue, candles, last close, last volume)`` (so another feed's
minute is another ask), a failure (offline, warming, error) only ``AHEAD_NEGATIVE_TTL_SEC`` before it is asked again.
One ask per symbol at a time; a newer minute waits for the next poll (nothing is queued), and the ask's done-callback
always clears it, even when the ask raised. ``generated_at`` (the desk clock) is never before ``as_of``.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import math
import time
from collections import OrderedDict
from typing import Any

from ahead import client, config, inputs, view
from ahead.client import ForecasterError
from constants_ahead import (
    AHEAD_BREAKER_FAILS,
    AHEAD_BREAKER_SEC,
    AHEAD_CACHE_MAX,
    AHEAD_ERROR,
    AHEAD_HEALTH_RETRY_SEC,
    AHEAD_HEALTH_TTL_SEC,
    AHEAD_MAX_TAIL_GAP_SEC,
    AHEAD_MIN_BARS,
    AHEAD_NEGATIVE_TTL_SEC,
    AHEAD_NOT_ENOUGH_BARS,
    AHEAD_NOT_SET_UP,
    AHEAD_OFFLINE,
    AHEAD_PENDING,
    AHEAD_PENDING_RETRY_MS,
    AHEAD_QUIET,
    AHEAD_READY,
    AHEAD_STATUS_WAIT_SEC,
    AHEAD_STEP_SEC,
    AHEAD_WARMING,
    AHEAD_WORDS_ASK_FAILED,
    AHEAD_WORDS_FUTURE_BAR,
    AHEAD_WORDS_PENDING,
    AHEAD_WORDS_WARMING,
)

logger = logging.getLogger(__name__)

Key = tuple[str, float, str, int, float, float]   # (symbol, as_of, venue, candles, last close, last volume)
Result = dict[str, Any] | ForecasterError

_cache: OrderedDict[Key, tuple[float, Result]] = OrderedDict()    # key -> (monotonic when stored, result)
_inflight: dict[str, tuple[Key, asyncio.Task]] = {}
_health: tuple[float, Result] | None = None                        # (monotonic when read, health or failure)
_breaker = {"fails": 0, "open_until": 0.0}


def reset_for_testing() -> None:
    global _health
    _cache.clear()
    _inflight.clear()
    _health = None
    _breaker.update(fails=0, open_until=0.0)
    client.reset_pool()
    inputs.reset_pool()


# ---------------------------------------------------------------- memory


def _store(key: Key, value: Result) -> None:
    _cache[key] = (time.monotonic(), value)
    _cache.move_to_end(key)
    while len(_cache) > AHEAD_CACHE_MAX:
        _cache.popitem(last=False)


def _cached(key: Key) -> Result | None:
    """A kept forecast, or a failure younger than the negative TTL; None asks again."""
    hit = _cache.get(key)
    if hit is None:
        return None
    at, value = hit
    if isinstance(value, ForecasterError) and time.monotonic() - at >= AHEAD_NEGATIVE_TTL_SEC:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return value


def _known_health() -> dict[str, Any] | None:
    """The forecaster's last good health (its model and exam on every answer), however old."""
    if _health is not None and isinstance(_health[1], dict):
        return _health[1]
    return None


async def _health_now() -> tuple[Result, bool]:
    """``(health or failure, asked)``: a ready health is trusted ``AHEAD_HEALTH_TTL_SEC``, anything else
    ``AHEAD_HEALTH_RETRY_SEC``."""
    global _health
    if _health is not None:
        at, value = _health
        ttl = AHEAD_HEALTH_TTL_SEC if isinstance(value, dict) and value["state"] == "ready" else AHEAD_HEALTH_RETRY_SEC
        if time.monotonic() - at < ttl:
            return value, False
    try:
        value = await client.run_ask(client.health)
    except ForecasterError as exc:
        value = exc
    _health = (time.monotonic(), value)
    return value, True


# ---------------------------------------------------------------- the breaker


def _breaker_left() -> float:
    return max(0.0, _breaker["open_until"] - time.monotonic())


def _breaker_count(failed: bool) -> None:
    """A miss counts; any answer (even a refusal) clears the count. Past the limit, one more miss reopens it."""
    if not failed:
        _breaker["fails"] = 0
        return
    _breaker["fails"] += 1
    if _breaker["fails"] >= AHEAD_BREAKER_FAILS:
        _breaker["open_until"] = time.monotonic() + AHEAD_BREAKER_SEC
        logger.warning("ahead: the forecaster missed %d answers in a row; asking again in %.0f s",
                       _breaker["fails"], AHEAD_BREAKER_SEC)


# ---------------------------------------------------------------- asking


async def _ask(key: Key, body: dict[str, Any], asked_at: float) -> None:
    """Ask once for ``key`` and keep what came back (a forecast or the failure)."""
    started = time.monotonic()
    try:
        health, asked = await _health_now()
        if isinstance(health, ForecasterError):
            if asked:
                _breaker_count(health.transport)
            raise health
        if health["state"] == "warming":
            raise ForecasterError(AHEAD_WARMING, health["detail"] or AHEAD_WORDS_WARMING)
        if health["state"] == "error":
            raise ForecasterError(AHEAD_ERROR, health["detail"] or "the forecaster reports an error")
        try:
            result = await client.run_ask(client.forecast, body)
        except ForecasterError as exc:
            _breaker_count(exc.transport)
            raise
        _breaker_count(False)
        # When Nova received it, on the desk clock the ask was made by (the playhead on a replay).
        _store(key, {**result, "issued_at": asked_at + (time.monotonic() - started)})
    except ForecasterError as exc:
        _store(key, exc)


def _done(sym: str, key: Key, task: asyncio.Task) -> None:
    entry = _inflight.get(sym)
    if entry is not None and entry[1] is task:
        del _inflight[sym]
    if task.cancelled():
        logger.info("ahead: the ask for %s was cancelled; the next poll asks again", sym)
        return
    exc = task.exception()
    if exc is not None:
        logger.error("ahead: asking the forecaster for %s failed", sym, exc_info=exc)
        _store(key, ForecasterError(AHEAD_ERROR, AHEAD_WORDS_ASK_FAILED))


def _asking(sym: str) -> bool:
    entry = _inflight.get(sym)
    if entry is None:
        return False
    task = entry[1]
    if task.done() or task.get_loop().is_closed():      # a loop that went away never runs its callback
        del _inflight[sym]
        return False
    return True


def _start(sym: str, key: Key, body: dict[str, Any], now: float) -> None:
    task = asyncio.get_running_loop().create_task(_ask(key, body, now))
    _inflight[sym] = (key, task)
    task.add_done_callback(functools.partial(_done, sym, key))


# ---------------------------------------------------------------- the answers


def _from_failure(exc: ForecasterError, n: int, health: dict[str, Any] | None) -> dict[str, Any]:
    if exc.state == AHEAD_NOT_ENOUGH_BARS:
        return view.ai_block(exc.state, reason=exc.message, need=exc.need or AHEAD_MIN_BARS, have=n, health=health)
    return view.ai_block(exc.state, reason=exc.message, health=health)


async def ahead(sym: str) -> dict[str, Any]:
    """The answer for ``sym`` at the desk clock: Nova's facts and the forecaster's view (or why there is none)."""
    now, replay = inputs.desk_now()
    desk_venue = inputs.venue()
    bars = await inputs.run_read(inputs.session_bars, sym, now, replay)
    prior = await inputs.run_read(inputs.prior_close, sym, replay)

    def reply(ai: dict[str, Any]) -> dict[str, Any]:
        return view.answer(sym=sym, now=now, replay=replay, venue=desk_venue, bars=bars, prior_close=prior, ai=ai)

    if not bars:
        return reply(view.ai_block(AHEAD_NOT_ENOUGH_BARS, reason=f"Ahead needs {AHEAD_MIN_BARS} one-minute candles.",
                                   need=AHEAD_MIN_BARS, have=0))
    problem = config.setup_problem()
    if problem is not None:
        return reply(view.ai_block(AHEAD_NOT_SET_UP, reason=problem))
    health = _known_health()
    try:
        inputs.assert_causal(bars, now)
    except ValueError:
        logger.error("ahead: %s has a candle ending after the desk clock %.0f; nothing was asked", sym, now,
                     exc_info=True)
        return reply(view.ai_block(AHEAD_ERROR, reason=AHEAD_WORDS_FUTURE_BAR, health=health))
    if len(bars) < AHEAD_MIN_BARS:
        return reply(view.ai_block(AHEAD_NOT_ENOUGH_BARS, need=AHEAD_MIN_BARS, have=len(bars),
                                   reason=f"Ahead needs {AHEAD_MIN_BARS} one-minute candles; it has {len(bars)}.",
                                   health=health))
    as_of = bars[-1]["t"] + AHEAD_STEP_SEC
    gap = view.tail_gap(now, as_of)
    if gap > AHEAD_MAX_TAIL_GAP_SEC:
        return reply(view.ai_block(AHEAD_QUIET, reason=f"No trade in the last {round(gap / 60)} minutes.",
                                   health=health))
    left = _breaker_left()
    if left > 0:
        # Real seconds on every desk (a replay's playhead may be paused): the words say "in N s", not a clock time.
        return reply(view.ai_block(
            AHEAD_OFFLINE, retry_at=time.time() + left, health=health,
            reason=f"missed {AHEAD_BREAKER_FAILS} answers in a row; asks again in {math.ceil(left)} s"))
    key: Key = (sym, as_of, desk_venue, len(bars), bars[-1]["c"], bars[-1]["v"])
    hit = _cached(key)
    if isinstance(hit, ForecasterError):
        return reply(_from_failure(hit, len(bars), health))
    if hit is not None:
        return reply(view.ai_block(AHEAD_READY, health=health, forecast=hit, issued_at=hit["issued_at"]))
    if not _asking(sym):
        _start(sym, key, inputs.request_body(sym, bars, as_of, prior, desk_venue), now)
    return reply(view.ai_block(AHEAD_PENDING, reason=AHEAD_WORDS_PENDING, retry_ms=AHEAD_PENDING_RETRY_MS,
                               health=health))


async def status() -> dict[str, Any]:
    """Is a forecaster set up, and what its health says (asked at most every ``AHEAD_HEALTH_TTL_SEC``)."""
    checked = time.time()
    problem = config.setup_problem()
    if problem is not None:
        return view.status(configured=False, reason=problem, health=None, checked_at=checked)
    try:
        value, _asked = await asyncio.wait_for(asyncio.shield(_health_now()), AHEAD_STATUS_WAIT_SEC)
    except asyncio.TimeoutError:
        return view.status(configured=True, reason=f"the forecaster did not answer in {AHEAD_STATUS_WAIT_SEC:g} s",
                           health=None, checked_at=checked)
    if isinstance(value, ForecasterError):
        return view.status(configured=True, reason=value.message, health=None, checked_at=checked)
    reason = None if value["state"] == "ready" else (value["detail"] or f"the forecaster is {value['state']}")
    return view.status(configured=True, reason=reason, health=value, checked_at=checked)

