"""
Authoritative policy and thresholds for B.L.A.S.T.
Define scan cadence, filters, and tier rules here; import from this module in
`main.py` and elsewhere instead of scattering magic numbers.
"""

# ── Market cap tiers (USD) ────────────────────────────────────────────────
SMALL_CAP_MIN =   300_000_000   #  $300 M
SMALL_CAP_MAX = 2_000_000_000   #   $2 B
MID_CAP_MIN   = 2_000_000_000   #   $2 B
MID_CAP_MAX   = 10_000_000_000  #  $10 B
LARGE_CAP_MIN = 10_000_000_000  #  $10 B

# ── News flame thresholds (hours) ─────────────────────────────────────────
NEWS_FLAME_HOT_HOURS  =  2   # red badge    (0 –  2 h)
NEWS_FLAME_WARM_HOURS = 12   # orange badge (2 – 12 h)
NEWS_FLAME_MAX_HOURS  = 24   # yellow badge (12 – 24 h); hide above this

# ── Relative volume ────────────────────────────────────────────────────────
REL_VOLUME_HIGH = 2   # highlight threshold

# ── Gapper filter ───────────────────────────────────────────────────────────
# Gap is (last price − previous close) / previous close, expressed as % for this threshold.
GAPPER_MIN_GAP_PCT = 10.0   # exclude symbols below this gap %

# ── Scanner sizing ──────────────────────────────────────────────────────────
SCAN_CAP_DEFAULT = 800   # max symbols scanned per discovery pass
TOP_N_DEFAULT = 50       # max gappers / cap on movers API batching

# ── Scan intervals (seconds) ────────────────────────────────────────────────
# Real-time prices still come from the WebSocket; these control REST discovery cadence.
DISCOVERY_INTERVAL_SEC = 120.0   # full universe scan (pre-market)
FOCUS_INTERVAL_SEC = 30.0        # reconcile current gapper list
GAINERS_INTERVAL_SEC = 20.0      # market-hours screener refresh
CLOSED_INTERVAL_SEC = 60.0       # closed-hours background refresh
