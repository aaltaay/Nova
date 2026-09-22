"""Wire-safe JSON for the scanner and HOD Momo sockets (QA C32).

``json.dumps`` writes a bare ``NaN`` / ``Infinity`` token for a non-finite
float. Browsers' ``JSON.parse`` refuses those, so one NaN in the HOD
``initial`` frame hid the whole day's alerts behind "No alerts yet", and every
reconnect dropped it again. The REST path already refuses NaN (FastAPI
renders with ``allow_nan=False``); the sockets now match it: a non-finite
float is sent as ``null`` -- a stated absence -- and the dump itself is strict,
so a regression fails loudly here instead of silently in the browser.
"""
from __future__ import annotations

import json
import math
from typing import Any


def wire_safe(value: Any) -> Any:
    """Return ``value`` with every non-finite float replaced by ``None``.

    Walks dicts, lists and tuples; returns the same object when nothing needed
    changing so the common case allocates nothing.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        changed = False
        out: dict[Any, Any] = {}
        for key, item in value.items():
            safe = wire_safe(item)
            changed = changed or safe is not item
            out[key] = safe
        return out if changed else value
    if isinstance(value, (list, tuple)):
        items = [wire_safe(item) for item in value]
        if all(a is b for a, b in zip(items, value, strict=True)):
            return value
        return items
    return value


def dumps_wire(payload: Any) -> str:
    """``json.dumps`` for a socket frame: non-finite floats as null, NaN refused."""
    return json.dumps(wire_safe(payload), allow_nan=False)
