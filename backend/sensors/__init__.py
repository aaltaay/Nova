"""L2 Brain sensors -- read-only observation GET surface.

No Place / cancel / flatten. No autonomous orders.
"""
from __future__ import annotations

from sensors.envelope import SENSOR_STATUSES, build_envelope
from sensors.registry import SENSOR_IDS, list_catalog

__all__ = [
    "SENSOR_IDS",
    "SENSOR_STATUSES",
    "build_envelope",
    "list_catalog",
]
