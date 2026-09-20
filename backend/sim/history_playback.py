"""Bounded immutable selection; disk/index work never owns the playback lock."""
from __future__ import annotations

import bisect
import threading
from array import array
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from constants_sim import (
    SIM_HISTORY_MAX_SELECTION_PRINTS, SIM_HISTORY_QUOTE_CANDLES, SIM_HISTORY_TAPE_ROWS,
)
from sim import history_store as store
from sim.chart_replay import INTERVAL_SECONDS
from sim.history_cache import CandleCache, previous_close

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


_selection: Selection | None = None


def clear():
    global _selection, _generation
    with _lock:
        _generation += 1
        _selection = None


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


def _load(spec: dict) -> Selection:
    job = store.find(spec, 'trades')
    rows = (store.read_prints(job['id'], through=job['cursor'],
                             limit=SIM_HISTORY_MAX_SELECTION_PRINTS + 1) if job else [])
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
    selected = dict(spec, coverage_through=job['cursor'] if job else spec['start_ts'],
                    trade_count=len(rows), download_status=job['status'] if job else 'missing',
                    job_id=job['id'] if job else None)
    prints, eligible_keys = tuple(rows), array('q', (row['ts'] for row in eligible))
    return Selection(selected, prints, array('q', (row['ts'] for row in rows)), eligible,
                     eligible_keys, volumes, highs, lows, previous_close(spec['symbol'], spec),
                     CandleCache(selected, prints, eligible, eligible_keys))


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
            _selection = loaded
            session_clock.set_session_date(spec['date'])
            session_clock.set_window(spec['start'], spec['end'])
            if not same_window:
                session_clock.scrub_to_second(0)
            return dict(loaded.spec)


def bars(symbol: str, timeframe: str, limit: int, now: datetime):
    with _lock:
        selected = _selection
    if not selected or timeframe not in INTERVAL_SECONDS:
        return None
    return selected.candles.bars(symbol, timeframe, limit, now.timestamp())


def snapshot(symbol: str):
    from sim import session_clock
    with _lock:
        selected, now = _selection, session_clock.now_et()
    if not selected:
        return {'active': False}
    spec = selected.spec
    result = dict(active=symbol == spec['symbol'], symbol=symbol, as_of=now.isoformat(),
                  selection=dict(spec), prints=[], last=None, volume=None, source='completed_bars',
                  open=None, high=None, low=None, prev_close=None,
                  bid=None, ask=None, depth_available=False)
    if not result['active']:
        return result
    result['prev_close'] = selected.prev_close
    cutoff = min(now.timestamp(), spec['end_ts'])
    if selected.prints:
        end = bisect.bisect_right(selected.keys, cutoff)
        eligible_end = bisect.bisect_right(selected.eligible_keys, cutoff)
        reached = eligible_end - 1
        result.update(source='trades', volume=selected.volumes[reached] if eligible_end else 0,
                      last=selected.eligible[reached]['price'] if eligible_end else None,
                      open=selected.eligible[0]['price'] if eligible_end else None,
                      high=selected.highs[reached] if eligible_end else None,
                      low=selected.lows[reached] if eligible_end else None)
        start = max(0, end - SIM_HISTORY_TAPE_ROWS)
        result['prints'] = [dict(row, ordinal=i,
                                time=datetime.fromtimestamp(row['ts'], timezone.utc).isoformat(),
                                bid=None, ask=None, side=None)
                            for i, row in enumerate(selected.prints[start:end], start)][::-1]
    if result['source'] != 'trades' or cutoff >= spec['coverage_through']:
        candles = selected.candles.bars(symbol, '1Min', SIM_HISTORY_QUOTE_CANDLES, cutoff)
        if candles:
            result.update(last=candles[-1]['c'], volume=sum(row['v'] for row in candles),
                          open=candles[0]['o'], high=max(row['h'] for row in candles),
                          low=min(row['l'] for row in candles),
                          source='mixed' if result['prints'] else 'completed_bars')
    return result
