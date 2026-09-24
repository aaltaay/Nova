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
# The L2 sensor's spoof_hints: the book watcher's newest large pulls (ADR 033).
SENSOR_SPOOF_HINTS = 5

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

# Operator focus (ADR 033): what each desk window reports, joined into one answer.
FOCUS_SCHEMA_VERSION = 1
# A window (or the Electron main process) that has not reported for this long is gone.
FOCUS_STALE_SEC = 20.0
# A gone window's last report is forgotten after this long.
FOCUS_FORGET_SEC = 300.0
FOCUS_RECENT_KEEP = 20
FOCUS_REPORT_MAX_BODY_BYTES = 16384
FOCUS_MAX_TABS = 40
FOCUS_MAX_WINDOWS = 16
FOCUS_PAGES = ("trader", "desk", "scanner", "account", "bots", "records")
FOCUS_SYMBOL_SOURCES = ("trader_tab", "desk_board", "scanner_row")
FOCUS_REASONS = ("start", "focus", "blur", "visibility", "page", "symbol", "input", "heartbeat", "display")
FOCUS_NOTE = (
    "Which Nova window Windows has in front, and the page and symbol it shows. Where your eyes are cannot be "
    "known; last_input_ts is when you last clicked or typed in that window."
)
