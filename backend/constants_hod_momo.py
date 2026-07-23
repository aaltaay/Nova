"""HOD Momo engine + integrity. Domain constants (Phase 3)."""
from constants_scanner import *  # noqa: F403

# ── HOD Momo Scanner ──────────────────────────────────────────────────────────

import os as _os

# Cache file keys / prefixes (kept in constants so cache.py and hod_momo.py share one source)
HOD_MOMO_ALERTS_PREFIX = "hod-momo"
HOD_MOMO_HIGHS_PREFIX = "hod-momo-highs"


def _hod_momo_cache_root() -> str:
    return (
        _os.environ.get("NOVA_CACHE_DIR")
        or _os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        or _os.path.join(_os.path.dirname(__file__), ".cache")
    )


HOD_MOMO_CONFIG_FILE = _os.path.join(_hod_momo_cache_root(), "hod-momo-config.json")
HOD_MOMO_BLOCKLIST_FILE = _os.path.join(_hod_momo_cache_root(), "hod-momo-blocklist.json")

# Engine timing
# Anti-spam mute removed (2026-07-17): a 60s mute ≥ burst window starved the
# Warrior "(N in Xs)" badge. Burst/consolidation alone rate-limits emits.
HOD_MOMO_COOLDOWN_SEC = 0.0          # 0 = mute off; do not raise without revisiting burst
HOD_MOMO_CONSOLIDATION_SEC = 10.0    # batch same-ticker alerts (Warrior "N in Xs")
# HOD truth: last must be within this of session high (abs $ or relative).
HOD_MOMO_HOD_EPSILON_ABS = 0.01
HOD_MOMO_HOD_EPSILON_PCT = 0.001     # 0.1%
# Warrior BA101 / KB: HOD Momentum needs a *new* high-of-day (+ momentum), not
# every retest of an already-set high (that's Running Up). After an observed /
# tick-6 raise of the session high, allow requires_hod strategies this long
# while price stays near the high (KB: alert may confirm within ~1 minute).
HOD_MOMO_NEW_HOD_GRACE_SEC = 60.0
# Raw observability — when True, strategy float/RVOL/price gates are skipped
# (master = data-ready; HOD still requires high_seeded for requires_hod strats).
HOD_RAW_MODE = _os.environ.get("HOD_RAW_MODE", "").strip().lower() in (
    "1", "true", "yes", "on",
)
# Persist at most this often — writing the full day list on every emit freezes the API.
HOD_MOMO_ALERT_SAVE_INTERVAL_SEC = 5.0
HOD_MOMO_UNIVERSE_INTERVAL_SEC = 300.0  # refresh cadence for broad (full-asset) mode
# Ross-style focus: Top Gainer/Gapper shortlist + IBKR volume seeds — not the
# full US tape. Broad mode subscribed ~6k IEX symbols → zero trades (empty tab).
# Warrior Day Trade Dash scans the whole market; Nova approximates that by
# unioning Top % Gain/Lose with HOT_BY_VOLUME / TOP_VOLUME_RATE / MOST_ACTIVE.
HOD_MOMO_UNIVERSE_MODE_FOCUS = "focus"
HOD_MOMO_UNIVERSE_MODE_BROAD = "broad"
HOD_MOMO_UNIVERSE_MODE = HOD_MOMO_UNIVERSE_MODE_FOCUS
HOD_MOMO_FOCUS_REFRESH_SEC = 5.0     # how often to rebuild focus set from scanner caches
HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK = 200  # max symbols per Alpaca WS subscribe message
HOD_MOMO_SESSION_RESET_HOUR_ET = 4   # reset session state at 4:00 AM ET
HOD_MOMO_SESSION_RESET_POLL_SEC = 30.0  # background rollover check cadence
HOD_MOMO_SEED_REFRESH_SEC = 30.0     # IBKR volume-scanner seed cadence
# Squeeze surge cold-start: live ticks alone start empty, so strategy 10/11 get
# surge:None (or ~0%) when a name first joins the focus universe mid-move.
# Seed the rolling price buffer from recent 1-min bars once per symbol/session.
HOD_MOMO_SURGE_SEED_TIMEFRAME = "1Min"
HOD_MOMO_SURGE_SEED_BARS = 15          # last ~15 minutes of 1-min OHLCV (surge buffer only)
# HOD truth (session_high) is a *separate* concern from the 15-bar surge
# buffer above: it must see the symbol's whole current session (04:00 ET
# premarket open through now), not just the last 15 minutes, or a runner
# that made its actual high 30+ minutes before joining the active set would
# get a falsely-low seeded floor and fire a false "new HOD" on a mere retest.
# ~960 one-minute bars covers the full 04:00-20:00 ET extended session.
HOD_MOMO_FULL_SESSION_BAR_LIMIT = 1000
HOD_MOMO_SURGE_SEED_POLL_SEC = 1.0     # drain pending seed queue
HOD_MOMO_SURGE_SEED_MAX_PER_TICK = 2   # IBKR historical pacing — keep low
# Integrity / fail-loud data-flow checks (invisible-bug detectors).
HOD_MOMO_INTEGRITY_TICK_STALE_SEC = 15.0       # no HOD ticks while universe non-empty → fail
HOD_MOMO_INTEGRITY_TICK_WARN_SEC = 3.0         # soft warn before hard stale fail
HOD_MOMO_INTEGRITY_WARMUP_SEC = 45.0           # grace after process start before tick check fails
HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC = 240.0  # buffer span for "ready" (4 of 5 min window)
HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT = 40.0  # % of buffered symbols that must be ready
HOD_MOMO_INTEGRITY_SURGE_PENDING_WARN = 10     # pending historical seeds → warn
HOD_MOMO_INTEGRITY_POLL_SEC = 20.0             # background integrity logger cadence
HOD_MOMO_INTEGRITY_ENRICHED_MIN_PCT = 30.0     # snaps with rvol vs tracked snaps
SCANNER_INTEGRITY_CACHE_STALE_SEC = 120.0      # gappers/gainers/losers cache age → warn/fail
# Active evaluation set (capacity-bounded) — ADR 008: deterministic admission,
# no quotas. Former Momo first (guaranteed), then round-robin across ranked
# Gappers/Gainers/Afterhours (see hod_momo_active.build_active_set). Live SLO:
# quote/eval age p95 ≤2s, max ≤3s for every *active* symbol.
HOD_MOMO_ACTIVE_SET_CAPACITY = 40
HOD_MOMO_ACTIVE_HOT_PER_TICK = 10              # priority symbols every 1Hz tick
# hod_momo_session_focus.py's sticky/alert-history priority is retired from
# the active-set build path (REQ-HOD-005) but the module + constant below
# are left intact — still covered by their own unit tests.
HOD_MOMO_ACTIVE_SESSION_FOCUS_SLOTS = 8
HOD_MOMO_SESSION_FOCUS_MAX = HOD_MOMO_ACTIVE_SESSION_FOCUS_SLOTS
# Quiet L1 symbols (unchanged last) never re-fire quote listeners — heartbeat
# refreshes note_quote/note_evaluation so active-set SLOs stay honest.
# Heartbeat must keep p95 quote/eval age ≤2s. A 1s loop + 1.5s stale gate
# samples at ~2.0–2.2s and false-fails the SLO; refresh sooner.
HOD_MOMO_ACTIVE_HEARTBEAT_SEC = 0.5
HOD_MOMO_ACTIVE_HEARTBEAT_STALE_SEC = 0.75
# Quiet-tape strategy re-eval removed (2026-07-17): re-calling on_trade_update
# on a flat last amplified cold-start false HOD. Keep constant for tests/docs.
HOD_MOMO_ACTIVE_REEVAL_SEC = 5.0
HOD_MOMO_QUIET_REEVAL_ENABLED = False
# When integrity is failing, suppress new alert emits (banner stays loud).
HOD_MOMO_SUPPRESS_ALERTS_ON_INTEGRITY_FAIL = True
HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_P95_SEC = 2.0
HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC = 3.0
HOD_MOMO_INTEGRITY_ACTIVE_EVAL_P95_SEC = 2.0
HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC = 3.0
# Coverage <100% on a single newly-admitted explore name (39/40→98%) must not
# hard-fail the whole feed — quote/eval age gates catch real multi-symbol death.
# Below this floor (e.g. overnight 85%) still fails.
HOD_MOMO_INTEGRITY_ACTIVE_COVERAGE_FAIL_PCT = 90.0
# IBKR qualify/reqMktData failures (e.g. FRE as SMART USD) — skip from active
# set for this cooldown so explore does not permanently poison coverage.
HOD_MOMO_L1_SUBSCRIBE_FAIL_COOLDOWN_SEC = 300.0
HOD_MOMO_INTEGRITY_DISCOVERY_TO_EVAL_TARGET_SEC = 5.0
HOD_MOMO_FORMER_MOMO_STRATEGY_ID = 1  # empty former_momo_list → never fire
# Manual-only watchlist default seed (REQ-HOD-006) — user edits from here.
HOD_MOMO_FORMER_MOMO_DEFAULT_LIST = ["SPRC"]
HOD_MOMO_RUNNING_UP_STRATEGY_ID = 12  # Warrior Running Up — no HOD required
HOD_MOMO_STRATEGY_ID_MAX = 12
# Squeeze family — session-focus sticky L1 when these are evaluated (not every tick).
HOD_MOMO_SESSION_FOCUS_STRATEGY_IDS = frozenset({2, 10, 11})

# Enrichment loop intervals
HOD_MOMO_ENRICH_INTERVAL_SEC = 30.0          # batch snapshot enrichment cadence
HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC = 2.0  # fundamentals per-symbol drain cadence
HOD_MOMO_FUNDAMENTALS_BATCH_SIZE = 10            # symbols per fundamentals tick (warm up faster)
# mark_needs_fundamentals() only fires once (when float/52wk-high are unknown), so
# avg_volume/float/52wk-high are otherwise "fetch once, cache forever" for the life
# of the process. A multi-session runner (Former Momo list) whose fundamentals were
# first fetched days ago keeps an ancient avg_volume denominator while today's
# cumulative volume grows — pace RVOL explodes into the hundreds/thousands for that
# symbol while a same-day-flagged runner (fresh fetch) looks normal. The active
# heartbeat re-queues fundamentals for every active symbol on this cadence so
# avg_volume tracks yfinance's live (rolling) average instead of freezing at the
# first-ever fetch.
#
# Shorter than FUNDAMENTALS_CACHE_TTL (900s) on purpose: yfinance's own
# ``averageVolume`` visibly drifts within minutes for a symbol having an
# explosive-volume day (live-observed: a fresh fetch returned 3.3M shares for
# ATPC ~11 min after the process-start fetch had cached 13.6k — a 248x swing
# from Yahoo-side data alone, not from a bug in our fetch code). A 900s
# heartbeat cadence leaves a single bad/early read frozen for a full 15
# minutes; 300s gives ~3 chances per FUNDAMENTALS_CACHE_TTL window to catch up
# with a fast-drifting name while staying far under yfinance's practical
# throughput (40 active symbols / 10-per-tick batches easily drain in <10s).
HOD_MOMO_FUNDAMENTALS_REFRESH_SEC = 300.0

# Master gate defaults.
# Warrior HOD Momo = new HOD + *per-strategy* momentum (float/RVOL/surge bands).
# Master surge is OFF by default so Medium Float / Low Float Rel Vol strategies
# are not double-gated by a global 3%/5min filter that Warrior does not apply.
HOD_MOMO_MASTER_HOD_REQUIRED = True
HOD_MOMO_MASTER_SURGE_PCT = 0.0      # 0 = disabled; squeeze strategies keep their own surge
HOD_MOMO_MASTER_SURGE_WINDOW_MIN = 5  # minutes (used only when surge_pct > 0)
# Master RVOL retired (2026-07-17): master = data-ready (+ optional master surge).
# Per-strategy ``min_rvol`` is the RVOL gate (Float RelVol etc.). Soft bypass gone.
HOD_MOMO_MASTER_MIN_RVOL = 0.0
HOD_MOMO_MASTER_PREMARKET_MIN_RVOL = 0.0   # master RVOL retired — strategy-level only
HOD_MOMO_MASTER_AFTERHOURS_MIN_RVOL = 0.0

# Pace RVOL (Warrior "Relative Volume (Daily Rate)"): today_vol / (avg * elapsed_frac).
# Floor = ~14 min of the 04:00–16:00 ET volume day — avoids insane RVOL at 4:01.
HOD_MOMO_RVOL_PACE_FLOOR = 0.02
HOD_MOMO_RVOL_USE_PACE = True
# Warrior "Relative Volume (5 min %)": last-5m vol ÷ (avg_daily / bars_in_session).
# Session = 04:00–16:00 ET (720 min → 144 five-minute bars), matching pace RVOL day.
HOD_MOMO_RVOL_5MIN_WINDOW_SEC = 300
HOD_MOMO_RVOL_5MIN_SESSION_MINUTES = 720.0
# When True, typical 5-min volume uses a coarse ET time-of-day curve (open/close heavy).
HOD_MOMO_RVOL_5MIN_USE_TOD = True
# Cumulative fraction of daily volume by ET minute-of-day (midnight=0). Coarse U-shape.
# Interpolated between knots; last knot should be ~1.0 at end of extended session.
HOD_MOMO_RVOL_5MIN_TOD_CUM_FRAC: tuple[tuple[int, float], ...] = (
    (4 * 60, 0.00),       # 04:00 premarket open
    (9 * 60 + 30, 0.12),  # 09:30 RTH open
    (10 * 60, 0.28),      # open spike
    (12 * 60, 0.45),      # midday
    (15 * 60, 0.65),      # afternoon
    (16 * 60, 0.88),      # RTH close
    (20 * 60, 1.00),      # 20:00 AH end
)

# RVOL fallback: when on IEX free tier, Alpaca historical bars are mostly empty.
# During warmup (first N seconds after startup), skip the RVOL master gate entirely
# so the scanner can fire while yfinance data loads progressively.
HOD_MOMO_RVOL_WARMUP_GRACE_SEC = 300            # 5 min: skip RVOL gate while yfinance warms up
# Bump when master/strategy defaults change so persisted configs migrate once.
HOD_MOMO_CONFIG_SCHEMA_VERSION = 7

# Strategy names (canonical order 1–12)
HOD_MOMO_STRATEGY_NAMES: dict[int, str] = {
    1:  "Former Momo Stock",
    2:  "Squeeze Alert - 52wk Breakout",
    3:  "Low Float - Med Rel Vol",
    4:  "Low Float - High Rel Vol - Price $20+",
    5:  "Low Float Volatility Hunter",
    6:  "Medium Float - High Rel Vol - Price under $20",
    7:  "Low Float - High Rel Vol",
    8:  "Medium Float - High Rel Vol - Price $20+",
    9:  "Medium Float - Med Rel Vol - Price $20+",
    10: "Squeeze Alert - Up 10% in 10min",
    11: "Squeeze Alert - Up 5% in 5min",
    12: "Running Up Alert",
}

# Strategy default colors (hex)
HOD_MOMO_STRATEGY_COLORS: dict[int, str] = {
    1:  "#FF9100",
    2:  "#FFD600",
    3:  "#66BB6A",
    4:  "#00BFA5",
    5:  "#FF5252",
    6:  "#B388FF",
    7:  "#00E676",
    8:  "#448AFF",
    9:  "#78909C",
    10: "#00E5FF",
    11: "#40C4FF",
    12: "#FF6E40",
}

# Audio ON by default for all except Former Momo (1) and Medium Float $20+ (8, 9)
HOD_MOMO_STRATEGY_AUDIO_DEFAULT: dict[int, bool] = {
    1: False, 2: True, 3: True, 4: True, 5: True,
    6: True, 7: True, 8: False, 9: False, 10: True, 11: True, 12: True,
}

# Per-strategy default config values.
# Keys match StrategyConfig field names. Missing keys use the universal 0-disabled default.
HOD_MOMO_STRATEGY_DEFAULTS: dict[int, dict] = {
    1: {  # Former Momo Stock — off until we have a real Warrior-aligned fill path
        "enabled": False,
        "min_rvol": 2.0,
        "former_momo_list": HOD_MOMO_FORMER_MOMO_DEFAULT_LIST,
    },
    2: {  # Squeeze Alert - 52wk Breakout
        "proximity_52wk_pct": 1.0,
        "min_rvol": 1.5,
        "surge_pct": 3.0,
        "surge_window_min": 5,
    },
    3: {  # Low Float - Med Rel Vol
        "max_float": 10_000_000,
        "min_rvol": 2.0,
        "max_rvol": 4.9,
    },
    4: {  # Low Float - High Rel Vol - Price $20+
        "max_float": 10_000_000,
        "min_rvol": 5.0,
        "min_price": 20.0,
    },
    5: {  # Low Float Volatility Hunter
        "max_float": 10_000_000,
        "min_rvol": 3.0,
        "min_change_pct": 5.0,
    },
    6: {  # Medium Float - High Rel Vol - Price under $20
        "min_float": 10_000_000,
        "max_float": 50_000_000,
        "min_rvol": 5.0,
        "max_price": 19.99,
    },
    7: {  # Low Float - High Rel Vol
        "max_float": 10_000_000,
        "min_rvol": 5.0,
    },
    8: {  # Medium Float - High Rel Vol - Price $20+
        "min_float": 10_000_000,
        "max_float": 50_000_000,
        "min_rvol": 5.0,
        "min_price": 20.0,
    },
    9: {  # Medium Float - Med Rel Vol - Price $20+
        "min_float": 10_000_000,
        "max_float": 50_000_000,
        "min_rvol": 2.0,
        "max_rvol": 4.9,
        "min_price": 20.0,
    },
    10: {  # Squeeze Alert - Up 10% in 10min — Warrior HOD widget requires new HOD
        "surge_pct": 10.0,
        "surge_window_min": 10,
        "requires_hod": True,
    },
    11: {  # Squeeze Alert - Up 5% in 5min — Warrior HOD widget requires new HOD
        "surge_pct": 5.0,
        "surge_window_min": 5,
        "requires_hod": True,
    },
    12: {  # Running Up Alert — Warrior separate scanner; momentum without HOD
        "requires_hod": False,
        "surge_pct": 5.0,
        "surge_window_min": 5,
        "min_rvol": 2.0,
    },
}

# ── Desktop (Electron) local API ──────────────────────────────────────────────
# Sidecar binds here; Electron UI always talks to this loopback address.
