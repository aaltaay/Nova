"""Selection-owned immutable archives and bounded candle results (ADR 017)."""
from __future__ import annotations

import bisect
import threading
from collections import OrderedDict
from datetime import datetime, timezone

from constants_sim import SIM_HISTORY_ARCHIVE_CACHE_ENTRIES, SIM_HISTORY_RESULT_CACHE_ENTRIES
from sim import history_coverage as coverage, history_store as store
from sim.chart_replay import (
    INTERVAL_SECONDS, aggregate_prints, extend_flat_tail, fill_flat_buckets, penny_bar,
)


def timestamp(row):
    return datetime.fromisoformat(row['t'].replace('Z', '+00:00')).timestamp()


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

    def _ranges(self):
        """Downloaded coverage; pre-range selections read as their contiguous prefix."""
        spec = self.spec
        if spec.get('coverage') is not None:
            return spec['coverage']
        through = spec.get('coverage_through', spec['start_ts'])
        return [[spec['start_ts'], through]] if through > spec['start_ts'] else []

    def _range_buckets(self, seconds):
        """Complete trade-built buckets that lie wholly inside one downloaded range.

        Aggregated and flat-filled per range, never across a gap: a stretch that
        was never downloaded must not be drawn as a quiet one. A bucket that
        straddles a range edge is not built here -- the archive bar stands in.
        """
        if seconds not in self.buckets:
            built = {}
            for a, b in self._ranges():
                lo, hi = bisect.bisect_left(self.keys, a), bisect.bisect_left(self.keys, b)
                rows = fill_flat_buckets(
                    [penny_bar(row) for row in aggregate_prints(self.eligible[lo:hi], seconds)], seconds)
                for row in extend_flat_tail(rows, seconds, b):
                    if row['ts'] >= a and row['ts'] + seconds <= b:
                        built[row['ts']] = row
            self.buckets[seconds] = built
        return self.buckets[seconds]

    def bars(self, symbol, timeframe, limit, cutoff):
        seconds = INTERVAL_SECONDS[timeframe]
        # Historical prints have second precision. Keep exact interval-close gates.
        cutoff = min(int(cutoff), self.spec['end_ts'])
        key = (symbol, timeframe, int(limit), cutoff)
        with self.lock:
            if key in self.results:
                self.results.move_to_end(key)
                return [dict(row) for row in self.results[key]]
            archive = self.archive(symbol, timeframe)
            if symbol == self.spec['symbol'] and self.prints:
                built = self._range_buckets(seconds)
                # Trades build what they wholly cover; the archive fills every
                # other completed bucket -- gaps, range edges, silent leads.
                result = [dict(row) for ts, row in archive
                          if ts + seconds <= cutoff and ts not in built]
                result += [self._out(row, seconds, cutoff) for ts, row in built.items()
                           if ts + seconds <= cutoff]
                # The forming bucket: prints reached so far (a print AT the playhead
                # second counts), drawn only when the playhead's own second is
                # downloaded and the bucket began inside that same range.
                current = cutoff // seconds * seconds
                in_range = coverage.range_at(self._ranges(), cutoff)
                if in_range and in_range[0] <= current:
                    reached = self.eligible[bisect.bisect_left(self.keys, current):
                                            bisect.bisect_right(self.keys, cutoff)]
                    result += [self._out(penny_bar(row), seconds, cutoff)
                               for row in aggregate_prints(reached, seconds)]
            else:
                result = [dict(row) for ts, row in archive if ts + seconds <= cutoff]
            result.sort(key=timestamp)
            value = tuple(result[-max(1, int(limit)):])
            bounded_put(self.results, key, value, SIM_HISTORY_RESULT_CACHE_ENTRIES)
            return [dict(row) for row in value]

    @staticmethod
    def _out(row, seconds, cutoff):
        return dict(t=datetime.fromtimestamp(row['ts'], timezone.utc).isoformat(),
                    o=row['open'], h=row['high'], l=row['low'], c=row['close'],
                    v=row['volume'], partial=row['ts'] + seconds > cutoff)
