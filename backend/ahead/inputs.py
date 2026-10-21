"""What the forecaster is sent (ADR 065): the desk clock, the completed 1-minute candles and the prior close.

Every value comes from its owner and is read once per ask, so nothing after the desk clock reaches the forecaster:

- **the clock** is the Sim playhead on a replay desk (``sim.mode.is_replay_desk``; unreadable counts as a replay, the
  stock read's rule), else the wall clock;
- **the candles** are the replay chart's own completed candles at the playhead (``stock_read.replay_read.bars``) on a
  replay, else the chart store's (``sensors.feeds.get_bars``) with the forming minute dropped; then the newest
  session's from 04:00 ET (``stock_read.indicators.session_of``);
- **the prior close** is the loaded replay's own (``sim.prior_close`` resolved it when the replay loaded) on a replay,
  else the scanner row's or the L1 line's IBKR close -- the figures the quote head's change is measured from. Unknown
  is ``None``, never a close worked back from a percentage.

Reads only, on their own threads (``run_read``): never a chart fill, never an IBKR line opened.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from constants_ahead import AHEAD_BARS_LIMIT, AHEAD_HORIZON_MIN, AHEAD_READ_WORKERS, AHEAD_STEP_SEC

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
T = TypeVar("T")
_FIELDS = ("o", "h", "l", "c", "v")

_pool_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=AHEAD_READ_WORKERS, thread_name_prefix="ahead-read")
        return _pool


async def run_read(fn: Callable[..., T], *args: Any) -> T:
    """``fn(*args)`` on the reads' own threads (never the forecaster's, never the event loop)."""
    return await asyncio.get_running_loop().run_in_executor(_executor(), functools.partial(fn, *args))


def reset_pool() -> None:
    """Tests: drop the reads' threads; the next read makes new ones."""
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def desk_now() -> tuple[float, bool]:
    """``(now, replay)``: the playhead on a replay desk, else the wall clock. Read once per ask."""
    from sim.mode import is_replay_desk
    from stock_read import replay_read

    try:
        replay = bool(is_replay_desk())
    except Exception:
        logger.warning("ahead: the Sim live edge is unreadable -- the desk counts as a replay", exc_info=True)
        replay = True
    return (replay_read.playhead() if replay else time.time()), replay


def venue() -> str:
    """The desk venue the forecaster is told: ``live`` | ``paper`` | ``sim``."""
    from sim.mode import venue as desk_venue

    return desk_venue()


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


def _bar(raw: dict[str, Any]) -> dict[str, float] | None:
    try:
        out = {"t": float(raw["t"]), **{k: float(raw[k]) for k in _FIELDS}}
    except (KeyError, TypeError, ValueError):
        return None
    return out if all(math.isfinite(v) for v in out.values()) else None


def session_bars(sym: str, now: float, replay: bool) -> list[dict[str, float]]:
    """The newest session's completed 1-minute candles at ``now``, oldest first, as ``{t, o, h, l, c, v}`` floats."""
    if replay:
        from stock_read import replay_read

        raw = replay_read.bars(sym, "1Min", AHEAD_BARS_LIMIT, now)
    else:
        from sensors.feeds import get_bars

        stored, _source = get_bars(sym, "1Min", AHEAD_BARS_LIMIT)
        raw = [b for b in stored if float(b["t"]) + AHEAD_STEP_SEC <= now]
    bars = [b for b in (_bar(r) for r in raw) if b is not None]
    if len(bars) != len(raw):
        logger.warning("ahead: %d of %s's 1-minute candles were unreadable and are not sent", len(raw) - len(bars), sym)
    bars.sort(key=lambda b: b["t"])
    from stock_read.indicators import session_of

    return session_of(bars)


def _replay_prior_close(sym: str) -> float | None:
    from sim import capture_player, history_playback

    selected = history_playback.selected()
    if selected is not None and str(selected.spec.get("symbol") or "").upper() == sym:
        return _positive(selected.prev_close)
    state = capture_player.snapshot()
    if state is not None and str(state.symbol).upper() == sym:
        return _positive(state.prev_close)
    return None


def _live_prior_close(sym: str) -> float | None:
    from strategy.symbol_pillars import find_board_row, live_quote, raw_boards

    row, _board = find_board_row(sym, raw_boards())
    value = _positive((row or {}).get("prev_close"))
    if value is None:
        value = _positive((live_quote(sym) or {}).get("prev_close"))
    return value


def prior_close(sym: str, replay: bool) -> float | None:
    """The previous session's close from its owner, or None when unknown (said as null, never invented)."""
    try:
        return _replay_prior_close(sym) if replay else _live_prior_close(sym)
    except Exception:
        logger.warning("ahead: the prior close of %s could not be read; it is sent as unknown", sym, exc_info=True)
        return None


def assert_causal(bars: list[dict[str, float]], as_of: float) -> None:
    """Raise ``ValueError`` when any candle ends after ``as_of`` (the ask then fails closed, nothing is sent)."""
    late = [b["t"] for b in bars if b["t"] + AHEAD_STEP_SEC > as_of]
    if late:
        raise ValueError(f"{len(late)} candle(s) end after the forecast time")


def contiguous_tail(bars: list[dict[str, float]]) -> int:
    """How many of the newest candles are consecutive minutes (0 with none)."""
    if not bars:
        return 0
    n = 1
    for i in range(len(bars) - 1, 0, -1):
        if bars[i]["t"] - bars[i - 1]["t"] != AHEAD_STEP_SEC:
            break
        n += 1
    return n


def et_iso(ts: float) -> str:
    """Epoch seconds as an ET ISO time with its offset (the contract's spelling)."""
    return datetime.fromtimestamp(ts, ET).isoformat(timespec="seconds")


def request_body(sym: str, bars: list[dict[str, float]], as_of: float, prior: float | None,
                 desk_venue: str) -> dict[str, Any]:
    """``POST /v1/forecast``'s body: minutes with no trade are left out, never invented."""
    return {
        "symbol": sym,
        "as_of": et_iso(as_of),
        "horizon_min": AHEAD_HORIZON_MIN,
        "prior_close": prior,
        "venue": desk_venue,
        "bars": [{"t": et_iso(b["t"]), **{k: b[k] for k in _FIELDS}} for b in bars],
    }
