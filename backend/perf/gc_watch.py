"""Garbage-collection pauses (ADR 026).

A gen-2 collection stops every Python thread; no loop or handler number
shows it. ``gc.callbacks`` fire on the thread that triggered the collection,
which may be holding any lock -- so the callback takes none: it only bumps
cumulative integers, and the reader diffs two readings.
"""
from __future__ import annotations

import gc
import time

_started_ns = 0
_counts = [0, 0, 0]
_pause_ns = 0
_max_ns = 0  # reset by take(); a race loses at most one maximum
_installed = False


def _on_gc(phase: str, info: dict) -> None:
    global _started_ns, _pause_ns, _max_ns
    if phase == "start":
        _started_ns = time.perf_counter_ns()
        return
    if _started_ns:
        dur = time.perf_counter_ns() - _started_ns
        _started_ns = 0
        gen = int(info.get("generation", 0))
        if 0 <= gen < 3:
            _counts[gen] += 1
        _pause_ns += dur
        if dur > _max_ns:
            _max_ns = dur


def install() -> None:
    global _installed
    if not _installed:
        gc.callbacks.append(_on_gc)
        _installed = True


def uninstall() -> None:
    global _installed
    if _installed:
        try:
            gc.callbacks.remove(_on_gc)
        except ValueError:
            pass
        _installed = False


def read() -> tuple[tuple[int, int, int], int]:
    """Cumulative ``((gen0, gen1, gen2) collections, pause_ns)``."""
    return (_counts[0], _counts[1], _counts[2]), _pause_ns


def take_max_ms() -> float:
    """Longest single pause since the previous call, in ms."""
    global _max_ns
    worst, _max_ns = _max_ns, 0
    return round(worst / 1_000_000, 2)


def reset_for_tests() -> None:
    global _pause_ns, _max_ns, _started_ns
    uninstall()
    _counts[:] = [0, 0, 0]
    _pause_ns = _max_ns = _started_ns = 0
