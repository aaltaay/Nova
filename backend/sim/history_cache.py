"""Selection-owned immutable archives and bounded candle results (ADR 017)."""
from __future__ import annotations

import bisect
import logging
import threading
from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone

from constants_sim import SIM_HISTORY_ARCHIVE_CACHE_ENTRIES, SIM_HISTORY_RESULT_CACHE_ENTRIES
from sim import history_store as store
from sim.chart_replay import INTERVAL_SECONDS, aggregate_prints

logger = logging.getLogger(__name__)


def timestamp(row):
    return datetime.fromisoformat(row['t'].replace('Z', '+00:00')).timestamp()


def previous_close(symbol: str, spec: dict) -> float | None:
    """The previous session only; misses are immutable until explicit reload."""
    from bars_store import read
    from sim.trading_day import UnsupportedCalendarYear, last_trading_day
    try:
        prior = last_trading_day(date.fromisoformat(spec['date']) - timedelta(days=1))
    except UnsupportedCalendarYear as exc:
        # A selection whose own date is supported must not be refused wholesale
        # because its prior session falls off the calendar's lower edge. A miss
        # is already an established state here (prev_close is float | None), so
        # degrade to it loudly instead of failing the whole load.
        logger.warning("No prior session available for %s %s: %s", symbol, spec['date'], exc)
        return None
    last_minute = datetime.combine(prior, time(15, 59), store.ET).timestamp()
    daily_label = datetime.combine(prior, time(0, 0), timezone.utc).timestamp()
    for timeframe, ts in (('1Min', last_minute), ('1Day', daily_label)):
        rows = (read(symbol, timeframe, 1, from_ts=ts, through_ts=ts) or {}).get('bars') or []
        if rows:
            return float(rows[-1]['c'])
    return None


def bounded_put(cache, key, value, maximum):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > maximum:
        cache.popitem(last=False)


class CandleCache:
    """All locks here belong to one immutable selection, never to playback globals."""
    def __init__(self, spec: dict, prints: tuple, eligible: tuple, keys):
        self.spec, self.prints, self.eligible, self.keys = spec, prints, eligible, keys
        self.lock = threading.RLock()
        self.archives = OrderedDict()
        self.selected_archives = {}
        self.results = OrderedDict()
        self.buckets = {}
        # Every selected-symbol timeframe shares the same explicit load boundary.
        for timeframe in INTERVAL_SECONDS:
            self.archive(spec['symbol'], timeframe)

    def archive(self, symbol, timeframe):
        key = (symbol, timeframe)
        with self.lock:
            if key in self.selected_archives:
                return self.selected_archives[key]
            if key in self.archives:
                self.archives.move_to_end(key)
                return self.archives[key]
            from bars_store import read
            from ibkr.historical_derive import derive_from_1min
            seconds = INTERVAL_SECONDS[timeframe]
            spec = self.spec
            limit = (spec['end_ts'] - spec['start_ts']) // seconds + 1
            stored = read(symbol, timeframe, limit, from_ts=spec['start_ts'],
                          through_ts=spec['end_ts'] - seconds)
            retained = store.read_candles(symbol, spec['start_ts'], spec['end_ts'])
            if timeframe != '1Min':
                retained = derive_from_1min(retained, timeframe)
            merged = {timestamp(row): row for row in (stored or {}).get('bars', [])}
            for row in retained:
                ts = timestamp(row)
                if spec['start_ts'] <= ts and ts + seconds <= spec['end_ts']:
                    merged[ts] = row
            value = tuple((ts, dict(row)) for ts, row in sorted(merged.items()))
            if symbol == self.spec['symbol']:
                self.selected_archives[key] = value
            else:
                bounded_put(self.archives, key, value, SIM_HISTORY_ARCHIVE_CACHE_ENTRIES)
            return value

    def bars(self, symbol, timeframe, limit, cutoff):
        seconds = INTERVAL_SECONDS[timeframe]
        # Historical prints have second precision. Keep exact interval-close gates.
        cutoff = min(int(cutoff), self.spec['end_ts'])
        key = (symbol, timeframe, int(limit), cutoff)
        with self.lock:
            if key in self.results:
                self.results.move_to_end(key)
                return [dict(row) for row in self.results[key]]
            result = [dict(row) for ts, row in self.archive(symbol, timeframe)
                      if ts + seconds <= cutoff]
            if symbol == self.spec['symbol'] and self.prints:
                coverage = self.spec['coverage_through']
                result = [row for row in result if timestamp(row) + seconds > coverage]
                if seconds not in self.buckets:
                    rows = aggregate_prints(self.eligible, seconds)
                    self.buckets[seconds] = (rows, [row['ts'] for row in rows])
                buckets, bucket_keys = self.buckets[seconds]
                complete_end = bisect.bisect_right(bucket_keys, cutoff - seconds)
                current = cutoff // seconds * seconds
                reached = self.eligible[bisect.bisect_left(self.keys, current):
                    bisect.bisect_right(self.keys, min(cutoff, coverage - 1))]
                for row in buckets[:complete_end] + aggregate_prints(reached, seconds):
                    if row['ts'] + seconds > coverage and cutoff >= coverage:
                        continue
                    result.append(dict(t=datetime.fromtimestamp(row['ts'], timezone.utc).isoformat(),
                                       o=row['open'], h=row['high'], l=row['low'], c=row['close'],
                                       v=row['volume'], partial=row['ts'] + seconds > cutoff))
            result.sort(key=timestamp)
            value = tuple(result[-max(1, int(limit)):])
            bounded_put(self.results, key, value, SIM_HISTORY_RESULT_CACHE_ENTRIES)
            return [dict(row) for row in value]
