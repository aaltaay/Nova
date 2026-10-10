"""Bounded immutable selection; disk/index work never owns the playback lock.

The Sim scratch account follows the selection (ADR 020 decision 3): clearing a
loaded window or selecting a different one starts the account over, through
the lock-free ``sim.broker.reset_scratch_account``. Re-selecting the same
window (the download folding new ranges in) keeps it.

A window comes from one of two stores (ADR 046): an IBKR download
(``history_store``, whole-second prints, no bid/ask) or an import from the
operator's Massive flat files (``massive_store``, nanosecond prints, the NBBO and
1-minute bars). A Massive window answers bid and ask at the playhead, colours
its prints from the NBBO and draws its candles from its own bars only -- never
from the IBKR chart store.
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
    SIM_MASSIVE_MAX_SELECTION_QUOTES, SIM_MASSIVE_SOURCE,
)
from sim import history_coverage as coverage, history_depth, history_quotes, history_sides
from sim import history_store as store
from sim.chart_replay import INTERVAL_SECONDS
from sim.history_cache import CandleCache
from sim.history_session import session_open as _session_open, stats_scope as _stats_scope
from sim.prior_close import previous_close

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
    #: A Massive window's NBBO (ADR 046); None for an IBKR download or a day whose quotes are not on disk.
    quotes: history_quotes.QuoteSeries | None = None


_selection: Selection | None = None


def is_massive(spec: dict | None) -> bool:
    return bool(spec) and spec.get("source") == SIM_MASSIVE_SOURCE


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


def selected() -> Selection | None:
    """The loaded window itself (immutable; its rows are shared, never to be changed by a reader): the Sim
    eyes read their lanes' tape from it (``eyes.history_recording``)."""
    with _lock:
        return _selection


def with_live_download_status(spec: dict, jobs: list[dict] | None = None) -> dict:
    """``spec`` with its download status as of now, not as of the load (QA 2026-09-22, C38).

    The selection copies the job's status when it loads, so a worker that died
    left the tape saying "the download is fetching this moment now" for good.
    Only an active label is re-read: from ``jobs`` (the listing, already
    relabelled) when given, else from the store through the same rule.
    """
    job_id = spec.get("job_id")
    if spec.get("download_status") not in (*store.ACTIVE, "queued") or not job_id:
        return spec
    try:
        if jobs is not None:
            match = next((job for job in jobs if job.get("id") == job_id), None)
            current = match["status"] if match else spec["download_status"]
        elif is_massive(spec):
            from sim import massive_import, massive_store

            job = massive_store.get(job_id)
            current = massive_import.effective_status(job) if job else "missing"
        else:
            from sim import history_download

            current = history_download.effective_status(store.get(job_id))
    except Exception:
        logger.warning("Historical replay: download status unavailable; keeping the loaded label", exc_info=True)
        return spec
    return spec if current == spec["download_status"] else dict(spec, download_status=current)


def _sets_price(row: dict) -> bool:
    """Tape-eligible: an IBKR print not flagged ``unreported``; a Massive print whose conditions set a price."""
    return row.get('sets_price', True) is not False and not row.get('unreported')


def _load(spec: dict) -> Selection:
    if is_massive(spec):
        return _load_massive(spec)
    job = store.find(spec, 'trades')
    # Every stored print is inside a downloaded range, so read them all, in time
    # order -- coverage may have gaps once the worker has jumped to the playhead.
    rows = (store.read_prints(job['id'], limit=SIM_HISTORY_MAX_SELECTION_PRINTS + 1) if job else [])
    ranges = coverage.job_ranges(job) if job else []
    return _build(spec, rows, ranges, job['status'] if job else 'missing', job['id'] if job else None)


def _load_massive(spec: dict) -> Selection:
    """A window imported from the Massive flat files: whole or absent, never part of one.

    Nothing plays before an import that holds the window completes. An import that runs again (the day's
    quotes arrived after the first) leaves the stored rows whole until it replaces them in one transaction,
    so what it imported before keeps playing. Under a wider import (the stock-day) only the window's rows load.
    """
    from sim import massive_import, massive_store

    holder, job = massive_import.holder(spec)
    status = massive_import.effective_status(job) if job else 'missing'
    if holder is None:
        return _build(spec, [], [], status, job['id'] if job else None, minutes=[],
                      extra=dict(quote_status=None, quote_count=0, bar_count=0))
    between = (spec['start_ts'], spec['end_ts'])
    rows = massive_store.read_prints(holder['id'], spec['symbol'], limit=SIM_HISTORY_MAX_SELECTION_PRINTS + 1,
                                     between=between)
    minutes = massive_store.read_candles(holder['id'])
    quote_status = holder.get('quote_status')
    quotes = None
    if quote_status in ('complete', 'none'):
        quote_rows = massive_store.read_quotes(holder['id'], limit=SIM_MASSIVE_MAX_SELECTION_QUOTES + 1, between=between)
        if len(quote_rows) > SIM_MASSIVE_MAX_SELECTION_QUOTES:
            raise ValueError(f'Replay exceeds {SIM_MASSIVE_MAX_SELECTION_QUOTES:,} quotes; narrow the window')
        quotes = history_quotes.QuoteSeries(quote_rows)
    return _build(spec, rows, [list(between)], status, holder['id'], minutes=minutes, quotes=quotes,
                  extra=dict(quote_status=quote_status, quote_count=len(quote_rows) if quotes else 0,
                             bar_count=holder.get('bar_count', 0)))


def _build(spec: dict, rows: list[dict], ranges: list, status: str, job_id: str | None, *,
           minutes: list[dict] | None = None, quotes: history_quotes.QuoteSeries | None = None,
           extra: dict | None = None) -> Selection:
    if len(rows) > SIM_HISTORY_MAX_SELECTION_PRINTS:
        raise ValueError(f'Replay exceeds {SIM_HISTORY_MAX_SELECTION_PRINTS:,} prints; narrow the window')
    eligible = tuple(row for row in rows if _sets_price(row))
    volumes, highs, lows = array('d'), array('d'), array('d')
    total = 0
    for row in eligible:
        total += row['size']
        volumes.append(total)
        highs.append(max(highs[-1], row['price']) if highs else row['price'])
        lows.append(min(lows[-1], row['price']) if lows else row['price'])
    selected = dict(spec, coverage=ranges, covered_seconds=coverage.covered_seconds(ranges),
                    coverage_through=coverage.contiguous_through(ranges, spec['start_ts']),
                    trade_count=len(rows), download_status=status, job_id=job_id, **(extra or {}))
    # Keys are float seconds: an IBKR print's whole second, a Massive print's SIP time to the nanosecond.
    prints, eligible_keys = tuple(rows), array('d', (row['ts'] for row in eligible))
    return Selection(selected, prints, array('d', (row['ts'] for row in rows)), eligible,
                     eligible_keys, volumes, highs, lows, previous_close(spec['symbol'], spec['date']),
                     CandleCache(selected, prints, eligible, eligible_keys, minutes=minutes),
                     _session_open(selected, eligible, eligible_keys, ranges, minutes), quotes)


def select(spec: dict, request: dict | None = None):
    """Publish after loading; a newer select/clear fences a superseded disk load.

    ``request`` is the window asked for when ``spec`` is wider -- the Massive stock-day that holds it -- and
    decides where the playhead goes (``_place_massive_playhead``).
    """
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
            # Another source for the same hours is another tape: the account starts over too.
            same_window = previous is not None and all(
                previous.get(key) == spec.get(key) for key in ('symbol', 'date', 'start', 'end', 'source'))
            # Where the operator put the playhead, before the window changes under it (None: the wall clock's).
            placed = session_clock.now_et() if session_clock.placed() else None
            replay.clear_capture()
            history_depth.clear()
            history_sides.clear()
            _selection = loaded
            session_clock.set_session_date(spec['date'])
            session_clock.set_window(spec['start'], spec['end'])
            if is_massive(spec):
                _place_massive_playhead(spec, request or spec, previous, same_window, placed)
            elif not same_window:
                session_clock.scrub_to_second(0)
                # Another day (or window): the account starts over at its playhead.
                _scratch_account_starts_over("another historical window selected")
            return dict(loaded.spec)


def _place_massive_playhead(spec: dict, asked: dict, previous: dict | None, same_window: bool, placed) -> None:
    """A load from the files keeps the playhead where the operator placed it on that day inside both the window
    asked for and the one loaded (ADR 046 amendment 2026-10-09: a stock-day's import moved WFF's from 10:05 to
    09:15); otherwise it goes to the start of the window asked for. Widening the same symbol-day under a playhead
    that stays keeps the practice account; any other new window starts it over, as before."""
    from sim import session_clock

    stays = placed is not None and placed.date().isoformat() == spec['date'] and (
        max(spec['start_ts'], asked['start_ts']) <= placed.timestamp() <= min(spec['end_ts'], asked['end_ts']))
    same_day = previous is not None and all(previous.get(key) == spec.get(key) for key in ('symbol', 'date', 'source'))
    if stays:
        if not same_window:
            session_clock.scrub_to_second(placed.timestamp() - spec['start_ts'])
        if not same_day:
            _scratch_account_starts_over("another historical window selected")
    elif not same_window or placed is not None:
        # A re-select of the loaded window under the wall clock's playhead moves nothing (the quiet fold-in).
        session_clock.scrub_to_second(max(0.0, asked['start_ts'] - spec['start_ts']))
        if not same_window:
            _scratch_account_starts_over("another historical window selected")


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


def bid_before(symbol: str, ts: float) -> float | None:
    """The NBBO bid standing just before a print at ``ts`` (a Massive window); None without quotes there.

    The tape's own rule for a print's side (``history_quotes.attach_sides``): the last NBBO row
    strictly before it. An IBKR download carries no quotes, so it never has one.
    """
    with _lock:
        selected = _selection
    if not selected or selected.spec['symbol'] != symbol or selected.quotes is None or not len(selected.quotes):
        return None
    row = selected.quotes.before(float(ts))
    return row['bid'] if row else None


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
                  stats_scope='window', bid=None, ask=None, bid_size=None, ask_size=None,
                  bid_exchange=None, ask_exchange=None, quote_ts=None, quote_source=None, quote_status=None,
                  depth_available=False, depth=None, sides_recorded=0, sides_nbbo=0)
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
    massive = is_massive(spec)
    if massive:
        # The Massive files carry the NBBO, never depth: bid and ask at the playhead
        # (ADR 046), and with no recorded book a one-level ladder flagged l1_fallback.
        result.update(history_quotes.snapshot_fields(selected.quotes, cutoff, spec.get('quote_status')))
        if book is None:
            book = history_quotes.top_of_book(selected.quotes, symbol, cutoff)
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
        # Real sides only: from the window's own NBBO (Massive), else from the
        # local L2 recording where it decides them.
        if selected.quotes is not None:
            result['sides_nbbo'] = history_quotes.attach_sides(selected.quotes, result['prints'])
        else:
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
