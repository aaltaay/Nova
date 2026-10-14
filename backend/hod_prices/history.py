"""An hour of HOD prices, with logarithmic range reads instead of per-tick scans.

Numeric arrays keep prices out of the collector's container walk. The index
contains only those arrays' prices, never another stream or strategy decision.
"""
from __future__ import annotations

import math
import threading
from array import array
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Iterator, Sequence


class PriceHistory(Sequence[tuple[float, float]]):
    """Time-ordered prices; the writer supplies the same one-hour cutoff as before."""

    def __init__(self, points: Iterable[tuple[float, float]] = ()) -> None:
        self._lock = threading.Lock()
        self._times = array("d")
        self._prices = array("d")
        self._head = 0
        self._capacity = 1
        self._tree = array("d", [math.inf, math.inf])
        self.replace(points)

    def __len__(self) -> int:
        with self._lock:
            return len(self._times) - self._head

    def __getitem__(self, item: int | slice):
        with self._lock:
            size = len(self._times) - self._head
            if isinstance(item, slice):
                return [(self._times[self._head + i], self._prices[self._head + i])
                        for i in range(*item.indices(size))]
            index = item if item >= 0 else size + item
            if not 0 <= index < size:
                raise IndexError("price history index out of range")
            index += self._head
            return self._times[index], self._prices[index]

    def __iter__(self) -> Iterator[tuple[float, float]]:
        # A cold seed/diagnostic reader must not hold the writer's lock while
        # consuming a day's history, nor see arrays halfway through a rebuild.
        with self._lock:
            times, prices = self._times[self._head:], self._prices[self._head:]
        return zip(times, prices, strict=True)

    def replace(self, points: Iterable[tuple[float, float]]) -> None:
        """Replace from an ordered seed, preserving tied timestamps' order."""
        ordered = sorted(points, key=lambda point: point[0])
        with self._lock:
            self._replace(ordered)

    def _replace(self, ordered: list[tuple[float, float]]) -> None:
        self._times = array("d", (point[0] for point in ordered))
        self._prices = array("d", (point[1] for point in ordered))
        self._head = 0
        self._rebuild()

    def merge(self, points: list[tuple[float, float]], keep_seconds: float) -> int:
        """Merge normalized seed points with the current live history in one transaction."""
        with self._lock:
            merged = list(zip(self._times[self._head:], self._prices[self._head:], strict=True))
            existing = set(merged)
            added = 0
            for point in points:
                if point not in existing:
                    merged.append(point)
                    existing.add(point)
                    added += 1
            if merged:
                merged.sort(key=lambda point: point[0])
                cutoff = merged[-1][0] - keep_seconds
                start = bisect_left(merged, cutoff, key=lambda point: point[0])
                self._replace(merged[start:])
            return added

    def add(self, ts: float, price: float, cutoff: float) -> None:
        """Insert one update and prune, atomically for route readers."""
        with self._lock:
            if len(self._times) > self._head and ts < self._times[-1]:
                index = bisect_right(self._times, ts, lo=self._head)
                self._times.insert(index, ts)
                self._prices.insert(index, price)
                self._rebuild()
            else:
                self._times.append(ts)
                self._prices.append(price)
                if len(self._prices) > self._capacity:
                    self._rebuild()
                else:
                    self._write_leaf(len(self._prices) - 1, price)
            self._trim(cutoff)

    def trim_before(self, cutoff: float) -> None:
        with self._lock:
            self._trim(cutoff)

    def _trim(self, cutoff: float) -> None:
        self._head = bisect_left(self._times, cutoff, lo=self._head)
        if self._head and self._head * 2 >= len(self._times):
            self._times = self._times[self._head:]
            self._prices = self._prices[self._head:]
            self._head = 0
            self._rebuild()

    def _rebuild(self) -> None:
        self._capacity = 1 << (len(self._prices) - 1).bit_length() if self._prices else 1
        self._tree = array("d", [math.inf]) * (2 * self._capacity)
        for i, price in enumerate(self._prices):
            self._tree[self._capacity + i] = price if not math.isnan(price) else math.inf
        for i in range(self._capacity - 1, 0, -1):
            self._tree[i] = min(self._tree[2 * i], self._tree[2 * i + 1])

    def _write_leaf(self, index: int, price: float) -> None:
        node = self._capacity + index
        self._tree[node] = price if not math.isnan(price) else math.inf
        while node > 1:
            node //= 2
            self._tree[node] = min(self._tree[2 * node], self._tree[2 * node + 1])

    def _minimum(self, start: int, end: int) -> float:
        left, right = self._capacity + start, self._capacity + end
        low = math.inf
        while left < right:
            if left % 2:
                low = min(low, self._tree[left])
                left += 1
            if right % 2:
                right -= 1
                low = min(low, self._tree[right])
            left //= 2
            right //= 2
        return low

    def surge(self, window_min: int, method: str) -> float | None:
        """The plain buffer's inclusive-window calculation, using its exact prices."""
        with self._lock:
            if len(self._times) == self._head:
                return None
            start = bisect_left(self._times, self._times[-1] - window_min * 60, lo=self._head)
            if len(self._times) - start < 2:
                return None
            current = self._prices[-1]
            if method == "fixed_start":
                first = self._prices[start]
            else:
                # The reference starts with current, so a NaN current stays
                # unknown even when another price inside the window is finite.
                candidate = self._minimum(start, len(self._times))
                first = candidate if candidate < current else current
            if first <= 0:
                return None
            return (current - first) / first * 100.0
