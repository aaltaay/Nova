"""Heap census (#619): what the cyclic garbage collector walks on every full collection.

A full (gen-2) collection stops every Python thread while it walks every tracked
object. On 2026-09-29 the backend ran about one a minute, all day, and the median
one took ~430 ms (4.95 s at 09:33:57) -- with only ~60 ms of that from imported
code. The census names the rest: tracked objects by type, and the backend's
biggest module-level containers. Taking it walks the heap as well, so it pauses
the process about as long as one full collection: the recorder takes one some
minutes after start and then hourly, never in the opening minutes, and
``GET /api/perf/heap`` answers the last one while it is young.
"""
from __future__ import annotations

import gc
import itertools
import logging
import os
import sys
import threading
import time
import types
from collections import Counter, deque
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from constants_perf import (
    PERF_HEAP_QUIET_ET,
    PERF_HEAP_SCAN_CAP,
    PERF_HEAP_TOP,
    PERF_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_BACKEND = os.path.normcase(str(Path(__file__).resolve().parents[1]))
_CONTAINERS = (dict, list, set, frozenset, deque, tuple)

_lock = threading.Lock()
_last: dict[str, Any] | None = None


def census(top: int = PERF_HEAP_TOP, now: float | None = None) -> dict[str, Any]:
    """Tracked objects by type and the biggest holders. Pauses the process while it walks."""
    started = time.perf_counter()
    objs = gc.get_objects()
    tracked = len(objs)
    by_type = Counter(map(type, objs))
    del objs
    holders = sorted(_holders(), key=lambda h: -max(h["items"], h["nested_items"]))[:top]
    return {
        "schema_version": PERF_SCHEMA_VERSION,
        "generated_at": round(time.time() if now is None else now, 3),
        "elapsed_ms": round((time.perf_counter() - started) * 1e3, 1),
        "tracked": tracked,
        "allocated_blocks": sys.getallocatedblocks(),
        "gc": {
            "thresholds": list(gc.get_threshold()),
            "counts": list(gc.get_count()),
            "frozen": gc.get_freeze_count(),
            "stats": gc.get_stats(),
        },
        "process": process_memory(),
        "types": [{"type": _type_name(t), "count": n} for t, n in by_type.most_common(top)],
        "holders": holders,
    }


def latest(max_age_sec: float, persist=None) -> dict[str, Any]:
    """The last census while it is younger than ``max_age_sec``, else a new one (kept, and
    handed to ``persist``). The lock makes concurrent callers share one walk."""
    global _last
    with _lock:
        now = time.time()
        if _last is not None and now - _last["generated_at"] < max_age_sec:
            return {**_last, "cached": True}
        result = census(now=now)
        _last = result
    if persist is not None:
        persist({"kind": "heap", "ts": result["generated_at"], **result})
    return {**result, "cached": False}


def seconds_until_allowed(now: float) -> float:
    """0 outside the opening minutes (PERF_HEAP_QUIET_ET, weekdays), else the wait until they end."""
    et = datetime.fromtimestamp(now, _ET)
    if et.weekday() >= 5:
        return 0.0
    start, end = (dtime(*map(int, t.split(":"))) for t in PERF_HEAP_QUIET_ET)
    if not start <= et.time() < end:
        return 0.0
    return (datetime.combine(et.date(), end, _ET) - et).total_seconds()


def process_memory() -> dict[str, int | None]:
    """This process's memory as the OS reports it; null where the platform does not say."""
    out: dict[str, int | None] = {"private_bytes": None, "working_set_bytes": None,
                                  "peak_working_set_bytes": None, "page_faults": None}
    try:
        if sys.platform == "win32":
            out.update(_windows_memory())
        else:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            scale = 1 if sys.platform == "darwin" else 1024      # Linux reports KiB
            out.update(peak_working_set_bytes=int(usage.ru_maxrss) * scale, page_faults=int(usage.ru_majflt))
    except (OSError, AttributeError, ValueError, ImportError):
        logger.debug("perf heap: process memory unavailable", exc_info=True)
    return out


def reset_for_tests() -> None:
    global _last
    with _lock:
        _last = None


def _windows_memory() -> dict[str, int]:
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    get_info = kernel32.K32GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if not get_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.get_last_error(), "K32GetProcessMemoryInfo failed")
    return {"private_bytes": int(counters.PrivateUsage), "working_set_bytes": int(counters.WorkingSetSize),
            "peak_working_set_bytes": int(counters.PeakWorkingSetSize), "page_faults": int(counters.PageFaultCount)}


def _type_name(t: type) -> str:
    return t.__qualname__ if t.__module__ == "builtins" else f"{t.__module__}.{t.__qualname__}"


def _holders() -> list[dict[str, Any]]:
    """Module-level containers of the backend's own modules, the containers on module-level
    objects (a state singleton's dicts) and on its classes, and its lru_caches, each counted once."""
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for mod_name, mod in sorted(list(sys.modules.items()), key=lambda kv: kv[0]):
        path = getattr(mod, "__file__", None)
        if not path or not os.path.normcase(path).startswith(_BACKEND) or mod_name.startswith("tests"):
            continue
        for key, val in list(vars(mod).items()):
            if key.startswith("__") or isinstance(val, types.ModuleType):
                continue
            if isinstance(val, _CONTAINERS):
                _add(out, seen, f"{mod_name}.{key}", val)
            elif isinstance(val, type):
                if val.__module__ == mod_name:              # a class-level registry or cache
                    for attr, sub in list(vars(val).items()):
                        if not attr.startswith("__") and isinstance(sub, _CONTAINERS):
                            _add(out, seen, f"{mod_name}.{key}.{attr}", sub)
            elif callable(val):
                info = getattr(val, "cache_info", None)     # functools.lru_cache / cache
                if callable(info) and id(val) not in seen:
                    seen.add(id(val))
                    size = int(getattr(info(), "currsize", 0) or 0)
                    if size:
                        out.append({"name": f"{mod_name}.{key}", "kind": "lru_cache", "items": size,
                                    "nested_items": 0})
            else:
                attrs = getattr(val, "__dict__", None)
                if isinstance(attrs, dict):
                    for attr, sub in list(attrs.items()):
                        if not attr.startswith("__") and isinstance(sub, _CONTAINERS):
                            _add(out, seen, f"{mod_name}.{key}.{attr}", sub)
    return out


def _add(out: list[dict[str, Any]], seen: set[int], name: str, obj: Any) -> None:
    if id(obj) in seen:
        return
    seen.add(id(obj))
    items = len(obj)
    if items == 0:
        return
    out.append({"name": name, "kind": type(obj).__name__, "items": items, "nested_items": _nested(obj)})


def _nested(obj: Any) -> int:
    """Items one level down: the lengths of the containers inside, and of the containers
    on the objects inside (a dict of per-symbol objects holding lists). A copy of at most
    PERF_HEAP_SCAN_CAP values is read, so a writer on another thread cannot break the walk."""
    values = obj.values() if isinstance(obj, dict) else obj
    total = 0
    for v in list(itertools.islice(iter(values), PERF_HEAP_SCAN_CAP)):
        if isinstance(v, _CONTAINERS):
            total += len(v)
            continue
        attrs = getattr(v, "__dict__", None)
        if isinstance(attrs, dict):
            total += sum(len(a) for a in list(attrs.values()) if isinstance(a, _CONTAINERS))
    return total
