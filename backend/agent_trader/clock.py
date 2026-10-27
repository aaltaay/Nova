"""The seat's clock: the wall clock, one place for every module here (and for tests to pin)."""
from __future__ import annotations

import time


def now() -> float:
    return time.time()
