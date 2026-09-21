"""L2 Brain sensor tunables.

Owner: backend/sensors/. Observation sizes only -- no trip/clear levels.
"""
from __future__ import annotations

# Common envelope
SENSOR_STATUSES = ("live", "stub", "computed_stub")
SENSOR_DEFAULT_LIQUID_SYMBOL = "AAPL"
SENSOR_TICK_DOLLARS = 0.01  # listed common-stock tick for $ display; not a trip
SENSOR_BOOK_LEVELS = 5
SENSOR_TAPE_PRINTS = 20
SENSOR_BOOK_RING = 32
SENSOR_TAPE_RING = 64
SENSOR_BAR_LIMIT = 240
SENSOR_LAST_MOVE_LOOKBACK = 20
SENSOR_REGIME_BARS = 20
SENSOR_VWAP_SLOPE_SHORT = 5
SENSOR_VWAP_SLOPE_LONG = 15
SENSOR_MACD_FAST = 12
SENSOR_MACD_SLOW = 26
SENSOR_MACD_SIGNAL = 9
SENSOR_EMA_PERIODS = (9, 20, 200)
SENSOR_FLOW_SWEEP_MIN_PRINTS = 3

# Clock labels for sensor 8 (session phase). Not a computed chop detector.
SESSION_OPEN_AUCTION_END_MIN_ET = 9 * 60 + 45  # 09:45
SESSION_MORNING_MOMENTUM_END_MIN_ET = 11 * 60  # 11:00
SESSION_MIDDAY_END_MIN_ET = 15 * 60  # 15:00 (power hour starts)

# Sensor 16 local store
SENSOR_MEMORY_SCHEMA_VERSION = 1
SENSOR_MEMORY_FILENAME = "l2-brain-memory.json"
SENSOR_MEMORY_MAX = 50
SENSOR_MEMORY_DECISIONS = ("go", "no-go")

# Sensor 18 stub calendar (static; not Advice)
SENSOR_MACRO_EVENTS = (
    {
        "id": "fomc-placeholder",
        "kind": "FOMC",
        "title": "FOMC decision (schedule stub)",
        "scheduled_ts": None,
        "expected_impact": "high",
        "symbol": None,
    },
    {
        "id": "cpi-placeholder",
        "kind": "CPI",
        "title": "CPI print (schedule stub)",
        "scheduled_ts": None,
        "expected_impact": "high",
        "symbol": None,
    },
    {
        "id": "nfp-placeholder",
        "kind": "NFP",
        "title": "Nonfarm payrolls (schedule stub)",
        "scheduled_ts": None,
        "expected_impact": "high",
        "symbol": None,
    },
)
