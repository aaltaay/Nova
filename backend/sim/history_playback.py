"""Bounded immutable selection; disk/index work never owns the playback lock.

The Sim scratch account follows the selection (ADR 020 decision 3): clearing a
loaded window or selecting a different one starts the account over, through
the lock-free ``sim.broker.reset_scratch_account``. Re-selecting the same
window (the download folding new ranges in) keeps it.
"""
from __future__ import annotations

import bisect
import logging
import threading
from array import array
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from constants_sim import (
    SIM_HISTORY_MAX_SELECTION_PRINTS, SIM_HISTORY_QUOTE_CANDLES, SIM_HISTORY_TAPE_ROWS,
)
from sim import history_coverage as coverage, history_depth, history_sides
from sim import history_store as store
from sim.chart_replay import INTERVAL_SECONDS
from sim.history_cache import CandleCache, previous_close
from sim.history_session import session_open as _session_open, stats_scope as _stats_scope

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_load_lock = threading.Lock()
_generation = 0


@dataclass(frozen=True)
class Selection:
    spec: dict
    prints: tuple
    keys: array
    eligible: tuple
    eligible_keys: array
    volumes: array
    highs: array
    lows: array
    prev_close: float | None
    candles: CandleCache
    #: ``(ts, price)`` of the regular session's open (W7), or None when unknown.
    session_open: tuple[float, float] | None = None


_selection: Selection | None = None


def clear():
    global _selection, _generation
    with _lock:
        _generation += 1
        had_selection = _selection is not None
        _selection = None
    history_depth.clear()
    history_sides.clear()
    if had_selection:
        _scratch_account_starts_over("historical replay unloaded")


def _scratch_account_starts_over(reason: str) -> None:
    from sim import broker as _broker

    _broker.reset_scratch_account(reason)


@contextmanager
def capture_transition():
    """Atomically retire history and register capture intent, in history→capture order.

    The caller must hold this only for local state/clock publication, never disk
    work or callbacks that acquire the historical lock in another thread.
    """
    with _lock:
        previous = dict(_selection.spec) if _selection else None
        clear()
        yield previous


def status():
    with _lock:
        return dict(_selection.spec) if _selection else None


def with_live_download_status(spec: dict, jobs: list[dict] | None = None) -> dict:
    """``spec`` with its download status as of now, not as of the load (QA 2026-09-22, C38).

    The selection copies the job's status when it loads, so a worker that died
    left the tape saying "the download is fetching this moment now" for good.
    Only an active label is re-read: from ``jobs`` (the listing, already
    relabelled) when given, else from the store through the same rule.
    """
    job_id = spec.get("job_id")
    if spec.get("download_status") not in store.ACTIVE or not job_id:
        return spec
    try:
        if jobs is not None:
            match = next((job for job in jobs if job.get("id") == job_id), None)
            current = match["status"] if match else spec["download_status"]
        else:
            from sim import history_download

            current = history_download.effective_status(store.get(job_id))
    except Exception:
        logger.warning("Historical replay: download status unavailable; keeping the loaded label", exc_info=True)
        return spec
    return spec if current == spec["download_status"] else dict(spec, download_status=current)


def _load(spec: dict) -> Selection:
    job = store.find(spec, 'trades')
    # Every stored print is inside a downloaded range, so read them all, in time
    # order -- coverage may have gaps once the worker has jumped to the playhead.
    rows = (store.read_prints(job['id'], limit=SIM_HISTORY_MAX_SELECTION_PRINTS + 1) if job else [])
    ranges = coverage.job_ranges(job) if job else []
    if len(rows) > SIM_HISTORY_MAX_SELECTION_PRINTS:
        raise ValueError(f'Replay exceeds {SIM_HISTORY_MAX_SELECTION_PRINTS:,} prints; narrow the window')
    eligible = tuple(row for row in rows if not row.get('unreported'))
    volumes, highs, lows = array('d'), array('d'), array('d')
    total = 0
    for row in eligible:
        total += row['size']
        volumes.append(total)
        highs.append(max(highs[-1], row['price']) if highs else row['price'])
        lows.append(min(lows[-1], row['price']) if lows else row['price'])
    selected = dict(spec, coverage=ranges, covered_seconds=coverage.covered_seconds(ranges),
                    coverage_through=coverage.contiguous_through(ranges, spec['start_ts']),
                    trade_count=len(rows), download_status=job['status'] if job else 'missing',
                    job_id=job['id'] if job else None)
    prints, eligible_keys = tuple(rows), array('q', (row['ts'] for row in eligible))
    return Selection(selected, prints, array('q', (row['ts'] for row in rows)), eligible,
                     eligible_keys, volumes, highs, lows, previous_close(spec['symbol'], spec),
                     CandleCache(selected, prints, eligible, eligible_keys),
                     _session_open(selected, eligible, eligible_keys, ranges))


def select(spec: dict):
    """Publish after loading; a newer select/clear fences a superseded disk load."""
    global _selection, _generation
    from sim import replay, session_clock
    with _lock:
        _generation += 1
        generation = _generation
    # Only one large transient materialization at a time; readers keep old selection.
    with _load_lock:
        loaded = _load(spec)
        with _lock:
            if generation != _generation:
                raise ValueError('Historical selection changed while loading; retry the desired window')
            previous = _selection.spec if _selection else None
            same_window = previous is not None and all(
                previous[key] == spec[key] for key in ('symbol', 'date', 'start', 'end'))
            replay.clear_capture()
            history_depth.clear()
            history_sides.clear()
            _selection = loaded
            session_clock.set_session_date(spec['date'])
            session_clock.set_window(spec['start'], spec['end'])
            if not same_window:
                session_clock.scrub_to_second(0)
                # Another day (or window): the account starts over at its playhead.
                _scratch_account_starts_over("another historical window selected")
            return dict(loaded.spec)


def bars(symbol: str, timeframe: str, limit: int, now: datetime):
    with _lock:
        selected = _selection
    if not selected or timeframe not in INTERVAL_SECONDS:
        return None
    return selected.candles.bars(symbol, timeframe, limit, now.timestamp())


def prints_between(symbol: str, after_ts: float, through_ts: float) -> list[tuple[float, float]]:
    """Reported ``(ts, price)`` prints in ``(after_ts, through_ts]`` for practice fills.

    Unreported prints (odd-lot / Form T) are excluded, as they are from last and
    candles, so a practice order never fills on a print IBKR's own bars ignore.
    """
    with _lock:
        selected = _selection
    if not selected or selected.spec['symbol'] != symbol:
        return []
    through = min(float(through_ts), selected.spec['end_ts'])
    lo = bisect.bisect_right(selected.eligible_keys, float(after_ts))
    hi = bisect.bisect_right(selected.eligible_keys, through)
    return [(float(row['ts']), float(row['price'])) for row in selected.eligible[lo:hi]]


def snapshot(symbol: str):
    from sim import session_clock
    with _lock:
        selected, now = _selection, session_clock.now_et()
    if not selected:
        return {'active': False}
    spec = selected.spec
    selection = with_live_download_status(dict(spec)) if symbol == spec['symbol'] else dict(spec)
    result = dict(active=symbol == spec['symbol'], symbol=symbol, as_of=now.isoformat(),
                  selection=selection, prints=[], last=None, volume=None, source='completed_bars',
                  open=None, high=None, low=None, prev_close=None, session_open=None,
                  stats_scope='window', bid=None, ask=None, depth_available=False, depth=None,
                  sides_recorded=0)
    if not result['active']:
        return result
    result['prev_close'] = selected.prev_close
    cutoff = min(now.timestamp(), spec['end_ts'])
    # The regular session's open once the playhead has reached it -- never the
    # window's first print, which made a 13:00 window's Gap% 223% (W7).
    if selected.session_open is not None and cutoff >= selected.session_open[0]:
        result['session_open'] = selected.session_open[1]
    # Is the playhead's own second downloaded? Past the edge or in a gap it is not,
    # and the tape must not pass older prints off as this moment's. The window is
    # half-open, so at its end the playhead reads the window's last second -- a
    # finished download used to read "not downloaded" there (R28).
    probe = min(int(cutoff), int(spec['end_ts']) - 1)
    in_range = coverage.range_at(spec.get('coverage') or [], probe)
    result['covered'] = in_range is not None
    # An IBKR download carries no book, so depth is whatever the local recorder
    # happens to have archived for this second -- usually nothing (#309).
    book = history_depth.book_at(symbol, cutoff)
    if book is not None:
        result.update(depth=book, depth_available=True)
    if selected.prints:
        end = bisect.bisect_right(selected.keys, cutoff)
        eligible_end = bisect.bisect_right(selected.eligible_keys, cutoff)
        reached = eligible_end - 1
        result.update(source='trades', volume=selected.volumes[reached] if eligible_end else 0,
                      last=selected.eligible[reached]['price'] if eligible_end else None,
                      open=selected.eligible[0]['price'] if eligible_end else None,
                      high=selected.highs[reached] if eligible_end else None,
                      low=selected.lows[reached] if eligible_end else None)
        # The tape is the playhead's own range only: it never runs across a gap,
        # and an uncovered playhead shows none. `ordinal` is the stored sequence,
        # stable across the re-selects that fold new ranges in.
        first = bisect.bisect_left(selected.keys, in_range[0]) if in_range else end
        start = max(first, end - SIM_HISTORY_TAPE_ROWS)
        result['prints'] = [dict({k: v for k, v in row.items() if k != 'seq'}, ordinal=row.get('seq', i),
                                 time=datetime.fromtimestamp(row['ts'], timezone.utc).isoformat(),
                                 bid=None, ask=None, side=None)
                            for i, row in enumerate(selected.prints[start:end], start)][::-1]
        # Real sides only, from the local L2 recording where it decides them.
        result['sides_recorded'] = history_sides.attach_recorded_sides(symbol, result['prints'])
    # Candles stand in only where the playhead's own second is not downloaded:
    # `coverage_through` is the end of the FIRST range, so every later range
    # used to price the last from a cent-rounded candle close (QA 2026-09-22, R19).
    if result['source'] != 'trades' or in_range is None:
        candles = selected.candles.bars(symbol, '1Min', SIM_HISTORY_QUOTE_CANDLES, cutoff)
        if candles:
            result.update(last=candles[-1]['c'], volume=sum(row['v'] for row in candles),
                          open=candles[0]['o'], high=max(row['h'] for row in candles),
                          low=min(row['l'] for row in candles),
                          # Trades exist for this selection even when this second
                          # has none; only a trade-less selection is candles-only.
                          source='mixed' if selected.prints else 'completed_bars')
    result['stats_scope'] = _stats_scope(spec, result['source'], in_range)
    return result
