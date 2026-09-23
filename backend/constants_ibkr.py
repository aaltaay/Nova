"""IBKR live, discovery, setups, risk, L2. Domain constants (Phase 3)."""
from constants_scanner import *  # noqa: F403
from constants_scanner import SCANNER_MIN_PRICE

NOVA_DESKTOP_API_HOST = "127.0.0.1"
NOVA_DESKTOP_API_PORT = 8000

# ── Interactive Brokers (optional trading module) ──────────────────────────────
# Set IBKR_ENABLED=true in .env to activate.
# IBKR_GATEWAY_MODE=paper|live  → which Gateway port to connect (data / L2).
# Default is live (4001). The paper Gateway (4002) is legacy: by hand only
# (POST /api/ibkr/gateway-mode {mode: "paper"}), never an automatic fallback
# unless IBKR_PAPER_GATEWAY_FALLBACK opts in (ADR 020).
# IBKR_ORDERS_ENABLED=false     → master kill switch; default OFF so live Gateway
#                                 cannot place buys/sells until you opt in.
# IBKR_LIVE_TRADING_CONFIRMED   → second key required when gateway/account is live.
# IBKR_SHORT_ENABLED=false      → third key for opening shorts (Phase K / ADR 009).
# IBKR_FORCE_ONE_SHARE=True     → MASTER TEST QTY GATE (see below). Not a bug.
IBKR_HOST = "127.0.0.1"
IBKR_SHORT_ENABLED_DEFAULT = False
# Optional .env override when Gateway AccountType is ownership (INDIVIDUAL).
# cash | margin. Unset = classify from tokens, then BP vs cash, else Cash.
IBKR_ACCOUNT_CLASS_ENV = "IBKR_ACCOUNT_CLASS"
# BP <= cash * this → Cash. Mirror: frontend/src/ibkr/accountType.ts
IBKR_ACCOUNT_CLASS_CASH_MAX_BP_RATIO = 1.15
# BP >= cash * this (or BP >= ExcessLiquidity * this) → Margin. Else Cash.
IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO = 1.5

# ── MASTER TEST QTY GATE (intentional; remove with one flip) ───────────────────
# When True, ADR 007 `execution.service.execute` CAPS every place/bracket qty
# (and shares) on the **Live** venue at IBKR_FORCE_ONE_SHARE_QTY before
# validate/send: a size at or under the cap goes through as asked, a larger one
# is cut to the cap, and the IBKR send refuses anything still above it
# (`QTY_CAP_LIVE`). Paper and Sim -- Nova's practice accounts, fake money with
# buying power enforced -- send the size asked. The ticket states the cap
# (`qty_cap` on /api/ibkr/status, null on Paper / Sim) and the execution record
# stamps `forced_one_share` only when the cap actually changed the size.
# Protective sources (flatten / kill / cancel_working) are never clamped: they
# close the held position, and a clamped KILL left N-1 shares (QA R6).
#
# WHY: so a fat-finger preset can never size a real-money send.
# NOT A BUG: do not "fix" by deleting the clamp without flipping this off.
# HISTORY: forced every order to exactly 1 share until 2026-09-22; that day it
# became a cap of 10 on every venue, then the operator settled #444: one share
# on Live, no cap on Paper / Sim. The names are kept so the execution record
# and its readers are stable.
#
# CHANGE THE LIVE CAP (one line, no code): `IBKR_QTY_CAP=10` in the desk .env;
#   the default below applies when it is unset. The clamp, the IBKR send check,
#   /api/ibkr/status `qty_cap` and the ticket's copy all read that one value
#   (execution/qty_gate.py).
# REMOVE (one line): set IBKR_FORCE_ONE_SHARE = False
#   (or delete the `cmd = apply_force_one_share(cmd)` line in execution/service.py)
IBKR_FORCE_ONE_SHARE = True
IBKR_FORCE_ONE_SHARE_QTY = 1.0  # default max shares per Live place / bracket while the gate is on
IBKR_QTY_CAP_ENV = "IBKR_QTY_CAP"  # .env override of the Live default above (whole number >= 1)
# Tick-236 shortability freshness for order gates (seconds).
IBKR_SHORTABILITY_TTL_SEC = 60.0
# Shares thresholds for shortability states (IBKR tick 236 estimate).
IBKR_SHORTABLE_EST_MIN_SHARES = 10_000.0
IBKR_PAPER_PORT = 4002       # IB Gateway paper trading port
IBKR_LIVE_PORT = 4001        # IB Gateway live trading port
# Default 17 (not 1): clientId 1 is commonly held by zombie uvicorn/--reload
# workers → Error 326 "client id already in use" / hung connectAsync that can
# wedge the FastAPI event loop. Override with IBKR_CLIENT_ID in .env.
IBKR_CLIENT_ID = 17
# Qualified Stock contracts reused across cold snapshots. Bounded + cleared on
# READY so a day-long desk cannot keep every snapshotted Contract forever (D-024).
IBKR_QUALIFIED_CONTRACTS_MAX = 256
# Error 326 -- another process already holds this clientId (second API).
IBKR_ERROR_CLIENT_ID_IN_USE = 326
IBKR_MAX_DEPTH_SYMBOLS = 3   # IBKR plan cap: 3 simultaneous Level 2 streams
IBKR_DEPTH_NUM_ROWS = 10     # Bid/ask rows requested per side of the book
# SMART-routed depth requires isSmartDepth=True (TWS API ≥974). With False,
# IBKR rejects every SMART contract with error 10092 even when TotalView /
# OpenBook is subscribed — see PROBLEM_LOG 2026-07-13.
IBKR_DEPTH_SMART = True
# After the last DepthLadder WS viewer disconnects, keep the IBKR depth line
# alive briefly so React StrictMode remounts / fast reconnects can reattach
# without tearing down reqMktDepth (which flashes "Connecting depth…").
IBKR_DEPTH_RELEASE_GRACE_SEC = 0.75
# Header Day P&L / Net Liq / BP + Positions marks. Frontend mirror:
# ``IBKR_ACCOUNT_POLL_MS`` (<=1000). Orders/closed stay slower.
IBKR_ACCOUNT_POLL_SEC = 1
IBKR_RECONNECT_DELAY_SEC = 10  # Delay before reconnect attempt
# Hard wall for connectAsync — ib_async's own timeout= can fail to cancel when
# Gateway accepts TCP but never finishes the API handshake (zombie clientId).
IBKR_CONNECT_TIMEOUT_SEC = 8.0
# TWS API error code: "Deep market data is not supported for this combination
# of security type/exchange." Arrives asynchronously via errorEvent AFTER
# reqMktDepth() already returned successfully, so it can't be caught by a
# try/except around the call — see ibkr/depth.py._on_ib_error.
IBKR_ERROR_DEPTH_NOT_SUPPORTED = 10092
# Tick-by-tick Time & Sales subscription failures (async via errorEvent).
# 10089/10189: requires additional market-data subscription; 354: not subscribed.
IBKR_ERROR_TICK_BY_TICK_CODES = frozenset({10089, 10189, 354})
# "Only 10 simultaneous API scanner subscriptions are allowed." Arrives
# asynchronously via errorEvent; with RaiseRequestErrors=False (ib_async
# default) the request's own future still resolves to [] with no exception,
# so this must be caught via errorEvent, not try/except around the call —
# see ibkr/discovery.py._one_shot_scanner + recover_scanner_slots.
IBKR_ERROR_SCANNER_SLOT_EXHAUSTED = 322
# "Fractional-sized order cannot be placed via API. Please use desktop version…"
# Live Flatten of leftover lots (e.g. 0.0642) is accepted locally then cancelled
# with this code ~80ms later — see PROBLEM_LOG 2026-07-23 Error 10243.
IBKR_ERROR_FRACTIONAL_API = 10243
IBKR_FRACTIONAL_ORDER_API_MSG = (
    "IBKR API cannot place fractional-share orders (Error 10243). "
    "Close leftovers in TWS / IB Gateway desktop."
)
# Place/cancel while the IB connect-loop is wedged (historicals / cold work).
IBKR_LOOP_WEDGED_ORDER_MSG = (
    "IB loop wedged -- order was not sent. Wait for charts/historicals to "
    "finish. Do not restart the API."
)
# Informational: IB rewrote TIF from account preset to DAY. Does NOT cancel
# the order (ib_async <next> treats as warning; Nova also refuses to latch it).
IBKR_ERROR_TIF_PRESET = 10349
# Informational: outsideRth ignored for this order type/destination.
IBKR_ERROR_OUTSIDE_RTH_IGNORED = 2109
# Informational: order held until next RTH open (Warning 399).
IBKR_ERROR_HELD_UNTIL_OPEN = 399
# Soft order warnings -- never a reject, never the reject-modal title.
# Peers of 2109: held-until-open, TIF preset rewrite, cancel notice, data-farm OK.
IBKR_SOFT_ORDER_WARNING_CODES = frozenset({
    IBKR_ERROR_OUTSIDE_RTH_IGNORED,
    IBKR_ERROR_HELD_UNTIL_OPEN,
    IBKR_ERROR_TIF_PRESET,
    202,  # order canceled notice (informational)
    2104,
    2106,
    2108,
})
# Compliance / no-opening-trades (ZTG 2026-09-16). Hard reject.
IBKR_ERROR_NO_OPENING_TRADES = 201
# Fill latency detective (#177). MKT during RTH only; LMT working is expected.
FILL_AUDIT_MKT_RTH_WARN_MS = 2_000
FILL_AUDIT_MKT_RTH_DANGER_MS = 10_000
FILL_AUDIT_JSONL_FILENAME = "fill-latency.jsonl"
# Same-second submit (incl. -1ms clock skew) vs a multi-hour fill is not a
# real MKT delay -- it is a timezone-mislabelled IBKR execution.time.
FILL_AUDIT_SAME_SECOND_SUBMIT_MS = 2_000
FILL_AUDIT_TZ_OFFSET_SLACK_MS = 2_000
FILL_AUDIT_TZ_RESIDUAL_MAX_MS = 120_000
FILL_AUDIT_IMPOSSIBLE_MKT_FILL_MS = 3_600_000
FILL_AUDIT_FAST_TYPES = frozenset({"MKT", "MIT", "MOC"})
FILL_AUDIT_REASON_TIMEZONE_SHAPED = "timezone_shaped_clock"
FILL_AUDIT_REASON_IMPOSSIBLE = "impossible_fill_clock"
# IBKR submitted_at / filled_at are often whole-second stamps. Nova's
# millisecond clock can land up to ~999ms later in the same second
# (IMCC BUY 106411: place_to_fill_ms=-296). That is clock disagreement,
# not a fill before Place. Any negative face total is clock_skew / ok.
# This ceiling documents the usual rounding band; larger negatives stay
# calm too -- still not a time machine.
FILL_AUDIT_CLOCK_SKEW_MS = 1_000
FILL_AUDIT_REASON_CLOCK_SKEW = "clock_skew"
# Default TIF for all Nova API orders -- never leave blank (triggers 10349).
IBKR_ORDER_TIF_DEFAULT = "DAY"
# Per-order TIF values ExecutionCommand.tif accepts (#91). DAY stays the
# default, so a caller that omits tif is unchanged. Keep in sync with
# frontend constantGroups/trade_defaults.ts TRADE_DEFAULT_TIFS.
IBKR_ORDER_TIFS: tuple[str, ...] = ("DAY", "GTC")
# Connectivity lost / restored (async via errorEvent). 1100 = lost; 1101/1102 = restored.
IBKR_ERROR_CONNECTIVITY_CODES = frozenset({1100, 1101, 1102})
IBKR_ERROR_CONNECTIVITY_LOST = 1100
IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST = 1101
IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT = 1102
# Soft 1100 with socket still up and no 1101/1102 — force disconnect + redial.
# Owner: ibkr/session_watchdog.py -- a sibling IB-loop task, NOT the dialer
# itself (session_reconnect.reconnect_loop). A watchdog living inside the
# task it watches cannot fire once that task is the thing that froze -- see
# PROBLEM_LOG 2026-08-31 (IBKR session frozen 7h with transport up).
IBKR_UNUSABLE_FORCE_RECONNECT_SEC = 30.0
# How often session_watchdog checks stuck-unusable + dialer heartbeat.
IBKR_SESSION_WATCHDOG_INTERVAL_SEC = 5.0
# Dialer heartbeat (session_reconnect stamps this at the top of every
# _reconnect_once iteration). Worst legitimate single iteration is roughly
# IBKR_CONNECT_TIMEOUT_SEC (8s) + IBKR_EARN_USABLE_TIMEOUT_SEC (45s) below;
# this leaves a comfortable margin before the watchdog decides the dialer
# task itself is dead or frozen and force-respawns it.
IBKR_DIALER_HEARTBEAT_STALE_SEC = 75.0
# Bound on the cold_slot lock acquire (ibkr/ib_scheduler.py). Without this, a
# stranded lock (holder crashed/cancelled without releasing, or a caller
# stuck inside the IB request itself) blocks every future cold job forever
# with no exception and no log line -- exactly what happened 2026-08-31.
IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC = 20.0
# Overall deadline on earn_usable's warm-up phase (positions + completed
# orders), on top of each call's own internal timeout. Belt-and-suspenders:
# covers the case where an inner bound is bypassed (e.g. an ib_async request
# that does not honor Task cancellation) without needing to know why.
IBKR_EARN_USABLE_TIMEOUT_SEC = 45.0
# Preferred port listening but connectAsync times out (Gateway Authenticating /
# 2FA). Back off instead of thrashing clientId or alternate-port heal.
IBKR_AUTH_BACKOFF_SEC_INITIAL = 30.0
IBKR_AUTH_BACKOFF_SEC_MAX = 60.0
# Hard wall for reqPositionsAsync during earn_usable warm-up (mirrors completed).
IBKR_POSITIONS_TIMEOUT_SEC = 10.0
# Data-farm OK / broken notices (async). Not fatal alone but worth surfacing.
IBKR_ERROR_DATA_FARM_CODES = frozenset({2104, 2106, 2108})
# "Max number of tickers has been reached" -- keep OUT of IBKR_BENIGN_LOG_ERROR_CODES.
IBKR_ERROR_MAX_TICKERS = 101
# "Requested market data is not subscribed. Displaying delayed market data."
IBKR_ERROR_DELAYED_DATA_NOTICE = 10167
# "Requested market data requires additional subscription for API. ... Delayed
# market data is available." Common on paper Gateway when live MD is not shared
# from the funded account (2026-08-07).
IBKR_ERROR_MD_REQUIRES_SUBSCRIPTION = 10089
# D-076: IB's generic "Error validating request" code. IB Gateway also uses it
# to reject every order mutation while Configure > Settings > API > Read-Only
# API is ticked, so the code ALONE is not evidence of read-only -- the message
# has to name it (see IBKR_READ_ONLY_API_MARKERS). PROBLEM_LOG 2026-07-22.
IBKR_ERROR_READ_ONLY_API = 321
# Lowercase substrings that make an Error 321 a read-only rejection rather than
# some other validation failure. IB's own wording is "The API interface is
# currently in Read-Only mode."
IBKR_READ_ONLY_API_MARKERS = ("read-only", "read only", "readonly")
# reqMarketDataType: 1=live, 3=delayed; see ibkr.client.get_market_data_type().
IBKR_MARKET_DATA_TYPE_LIVE = 1
IBKR_MARKET_DATA_TYPE_DELAYED = 3
# Quote quality flag when ticks.py serves ticker.close because last is missing.
IBKR_QUOTE_QUALITY_CLOSE_FALLBACK = "close_fallback"

# ib_async's OWN internal loggers (ib_async.wrapper / .ib / .client — not our
# app loggers) log these at ERROR even though they're expected under normal
# Gateway operation. See backend/ibkr/log_filters.py (downgrade → WARNING so
# Sentry LoggingIntegration stops opening issues; local logs still see them).
# Keep Error 101 (max tickers) OUT — that is real capacity oversubscription.
# Live Sentry cross-check 2026-07-22: PYTHON-FASTAPI-C (300), -2S/-2Q (10089),
# -F/-PN (gateway port / ConnectionRefused), -SW/-SN (open/completed timeout).
IBKR_BENIGN_LOG_ERROR_CODES = frozenset({
    162,   # historical/scanner query cancelled
    365,   # no scanner subscription for ticker id
    300,   # Can't find EId — late cancel vs already-cleared reqId
    354,   # requested market data not subscribed
    200,   # no security definition (unknown/delisted contract)
    202,   # order canceled notice (informational)
    10349,  # TIF DAY preset notice (informational; not a hard cancel)
    322,   # scanner subscription quota (recovery path handles; avoid Sentry flood)
    326,   # client id already in use (reconnect race)
    366,   # no historical data query for ticker id (cancel race; sibling of 365)
    504,   # not connected (Gateway down / mid-reconnect)
    1100,  # connectivity lost (ops-once via stamp_unusable capture)
    1101,  # connectivity restored data lost (reconnect chatter)
    1102,  # connectivity restored data kept (reconnect chatter)
    10089,  # tick-by-tick / depth needs additional market-data subscription
    10189,  # same family as 10089
})
IBKR_BENIGN_LOG_MESSAGE_SUBSTRINGS = (
    "cancelmktdata: no reqid found",
    "cancelmktdepth: no reqid found",
    "cancelmktdata: no subscription for",
    "unknown reqid",
    "open orders request timed out",
    "completed orders request timed out",
    "make sure api port on tws/ibg is open",
    "api connection failed: connectionrefusederror",
    "peer closed connection",
)
# Ops-once Sentry fingerprint cooldown for session unusable / max tickers.
SENTRY_SESSION_UNUSABLE_COOLDOWN_SEC = 300.0
IBKR_GATEWAY_MODE_DEFAULT = "live"
IBKR_ORDERS_ENABLED_DEFAULT = False  # never spend until explicitly enabled
# Follow the listening Gateway when the preferred port is dark (paper -> live
# always; live -> paper only with the opt-in below).
# Override with IBKR_GATEWAY_SELF_HEAL=false. Spend gates never auto-unlock.
IBKR_GATEWAY_SELF_HEAL_DEFAULT = True
# ADR 020 (second pass, 2026-09-21): the IBKR paper Gateway (4002) is legacy.
# With market-data sharing on, a paper login beside a live session is
# read-only and carries no tape, so a desk that silently followed it would
# look connected while every scanner and Level 2 stayed dark. Follow-Gateway
# therefore never falls back to the paper port on its own. Opt in with
# IBKR_PAPER_GATEWAY_FALLBACK=true; POST /api/ibkr/gateway-mode
# {mode: "paper"} stays the by-hand door either way.
IBKR_PAPER_GATEWAY_FALLBACK = False
# After a user Paper/Live click, do not auto-follow the other port immediately
# (they may be launching the requested Gateway + 2FA). After this grace, if
# the requested port is still dark and the other is up, follow-Gateway resumes.
IBKR_INTENTIONAL_FOLLOW_GRACE_SEC = 120.0
# Terminal IBKR orderStatus values for Closed Orders (WID-027). Working /
# pending / partial-still-open stay on open_orders (WID-026).
IBKR_CLOSED_ORDER_STATUSES = frozenset({
    "Filled",
    "Cancelled",
    "ApiCancelled",
    "Inactive",
})
# Max rows returned by GET /api/ibkr/orders/closed (session trades only).
IBKR_CLOSED_ORDERS_LIMIT_DEFAULT = 100
# Hard ceiling for reqCompletedOrdersAsync — Read-Only Gateway / wedged API
# can hang forever without this; reconnect loop and GET /orders/closed both
# await the warm-up and must not block the event loop indefinitely.
IBKR_COMPLETED_ORDERS_TIMEOUT_SEC = 10.0
# Min seconds between completed-orders IBKR round-trips. Closed Orders UI polls
# every 5s; when the session has zero fills, closed_orders_async used to warm
# on every empty read and flood reqCompletedOrdersAsync (event-loop stalls /
# API_WEDGED). Connect warm-up passes force=True to bypass this cooldown.
IBKR_COMPLETED_ORDERS_MIN_INTERVAL_SEC = 300.0
# D-058: while completed orders are unanswered, re-ask this often on the IB
# loop so the desk warning clears as soon as the Gateway answers. Cheap while
# ib_async still holds the stale request (fails with no wire traffic).
IBKR_COMPLETED_ORDERS_REPROBE_SEC = 60.0
# D-058: only surface the warning once it has lasted this long, so a Gateway
# that is merely slow at connect (answers at ~8s vs the 7.5s sync) and
# recovers on the next re-probe never reaches the desk.
IBKR_COMPLETED_ORDERS_WARN_AFTER_SEC = 120.0
# D-057: completed orders are fetched AFTER the session is READY, never inside
# the connect warm-up (a Gateway that never answers reqCompletedOrders must not
# delay READY). These are the sleeps before attempt 2..N of that background
# warm; once they are spent, completed_orders_health.reprobe_loop keeps asking
# every IBKR_COMPLETED_ORDERS_REPROBE_SEC, so nothing is given up on.
IBKR_COMPLETED_ORDERS_WARM_BACKOFF_SEC = (2.0, 8.0, 30.0)

# User-initiated Gateway launch (header double-click → POST /api/ibkr/launch-gateway).
# Override with IBKR_GATEWAY_EXE; otherwise ibgateway.exe or IBC-renamed ibgateway1.exe.
IBKR_GATEWAY_ROOT = r"C:\Jts\ibgateway"
IBKR_GATEWAY_EXE_DEFAULT = r"C:\Jts\ibgateway\1045\ibgateway.exe"
# Optional IBC launcher (credentials stay outside git — see docs/ibc-gateway-setup.md).
# Join with Path.home() / ".nova" / "ibc" / "start_gateway.ps1" -- do not
# concatenate the backslash string on Linux Path (CI + Cloud).
IBKR_IBC_LAUNCHER_REL = r".nova\ibc\start_gateway.ps1"
IBKR_LAUNCH_MISSING_CREDS_MSG = (
    "Open live/paper cannot prefill Gateway username/password -- "
    "%USERPROFILE%\\.nova\\ibc\\config.ini is missing IbLoginId/IbPassword "
    "(set IbLoginIdLive / IbLoginIdPaper too). See docs/ibc-gateway-setup.md."
)
IBKR_LAUNCH_MISSING_IBC_MSG = (
    "Open live/paper cannot prefill Gateway login -- IBC launcher missing at "
    "%USERPROFILE%\\.nova\\ibc\\start_gateway.ps1. "
    "Copy scripts/start_gateway_ibc.ps1.example and install IBC. "
    "Raw ibgateway.exe leaves username/password empty."
)
# Both doors keep the week-long Gateway token (self-restart nightly, no daily
# cold 2FA) -- see PROBLEM_LOG 2026-08-25. A routine launch/attach never clears
# it; only an explicit re-auth (force_fresh_login) does, via jts_ini.clear_restart_token.
IBKR_IBC_PAPER_AUTO_RESTART_TIME = "11:45 PM"
IBKR_IBC_LIVE_AUTO_RESTART_TIME = "11:45 PM"
# Gateway jts.ini Restart=OK reuses the week session and skips the 2FA code box.
IBKR_JTS_INI_PATHS = (
    r"C:\Jts\ibgateway\1045\jts.ini",
    r"C:\Jts\jts.ini",
)
# Owner: ibkr/gateway_trail.py. Append-only Paper/Live click + attach/refuse.
IBKR_GATEWAY_TRAIL_FILENAME = "ibkr-gateway-trail.jsonl"
IBKR_GATEWAY_TRAIL_MAX_EVENTS = 200
# Owner: ibkr/second_factor.py. Mirrors the local IBC config.ini's own
# SecondFactorAuthenticationTimeout (180s) -- IBC silently discards and
# retries a Second Factor prompt once it has sat open longer than this, even
# if the operator approves it a moment later (see PROBLEM_LOG 2026-08-25).
# Keep in sync with config.ini; do not tune independently of that file.
IBKR_SECOND_FACTOR_STALE_AFTER_SEC = 180.0

# ── Market-data discovery provider (gappers / gainers / losers source) ────────
# Product lock: IBKR is the only scanner discovery source. Alpaca scanner
# adapters remain in-repo for emergency/unit use but are not selectable via
# Settings or /api/config. Alpaca still serves news headlines + Assets listing
# flags (not prices). See Scanner-Provider-IBKR-Primary.md.
DISCOVERY_PROVIDER_DEFAULT = "ibkr"
DISCOVERY_PROVIDER_OPTIONS = ("ibkr",)

# IB market scanner — https://interactivebrokers.github.io/tws-api/market_scanners.html
# Limits enforced by IB itself: max 50 rows per scan code, max 10 active scans.
IBKR_SCAN_INSTRUMENT = "STK"
IBKR_SCAN_LOCATION = "STK.US.MAJOR"            # all major US exchanges
IBKR_SCAN_CODE_GAPPERS = "TOP_OPEN_PERC_GAIN"  # today's open vs prior close (premarket gap)
IBKR_SCAN_CODE_GAINERS = "TOP_PERC_GAIN"       # current price vs prior close, intraday
IBKR_SCAN_CODE_LOSERS = "TOP_PERC_LOSE"
# Dedicated after-hours movers — distinct scan universe from TOP_PERC_GAIN
# (extended-hours session only). Used as the PRIMARY After Hours tab source;
# reshaping the intraday gainer_cache is a fallback only for when this scan
# is empty (thin AH liquidity / IB scanner gaps), never the primary source.
IBKR_SCAN_CODE_AH_GAINERS = "TOP_AFTER_HOURS_PERC_GAIN"
IBKR_SCAN_CODE_AH_LOSERS = "TOP_AFTER_HOURS_PERC_LOSE"
IBKR_SCAN_MAX_ROWS = 50                        # IB hard cap per scan code
IBKR_SCAN_ABOVE_PRICE = SCANNER_MIN_PRICE       # mirrors the Alpaca price floor above
# Legacy / cold-path snapshot tunables (NOT the active-table freshness SLA).
# IB completes snapshots on tickSnapshotEnd ~11s later — never use a 4s timeout
# for live table freshness. Active tab + HOD use reqMktData L1 streams instead.
IBKR_TABLE_REPRICE_MAX_SYMBOLS = 100
IBKR_TABLE_REPRICE_CHUNK_SIZE = 20
# ADR 010 -- cold reqTickersAsync batch. Never 40-wide on the IB loop.
IBKR_COLD_SNAPSHOT_BATCH = 5
IBKR_QUOTE_BATCH_TIMEOUT_SEC = 15.0             # cold/discovery reqTickersAsync (≥12s)
# Coalesce duplicate reqScannerDataAsync calls for the same (scan_code,
# below_price) within this window. Movers refresh, gapper's TOP_PERC_GAIN
# fallback, and the HOD seed loop each call scan_symbols() independently —
# without this, the same scan code can be re-queried against IB several
# times within one burst for identical results.
IBKR_SCAN_RESULT_TTL_SEC = 5.0
IBKR_TABLE_REPRICE_CHUNK_TIMEOUT_SEC = 12.0     # honest snapshot budget (was 4s — impossible)
IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC = 25.0        # thread->asyncio bridge wait ceiling
# Cap concurrent run_coro bridges when the uvicorn loop is wedged (lag streak).
IBKR_RUN_CORO_MAX_INFLIGHT = 12
IBKR_RUN_CORO_MAX_INFLIGHT_WHEN_WEDGED = 2
# Local wall on reqScannerDataAsync itself, inside the bridge ceiling above —
# an unbounded scanner call previously could not be distinguished from any
# other cause of a bridge timeout. Set below the bridge ceiling so a hung
# scanner call is attributable (and cancellable) before the outer wall fires.
IBKR_SCAN_REQUEST_TIMEOUT_SEC = 20.0
# ADR 008 — persistent scanner manager (ibkr/scanner_stream.py). Authoritative
# cutover on (2026-08-07): shadow+one-shot dual pipeline starved the UI —
# empty-shadow quiet forever, then competing TOP_PERC_* oneshots timed out
# against the same clientId leases. Env override still wins.
IBKR_SCANNER_PERSISTENT_ENABLED = True
IBKR_SCANNER_PERSISTENT_AUTHORITATIVE = True
# One-shot scan_loop discovery defers to the persistent stream for this many
# seconds after READY (see scanner_stream.in_ready_quiet_window). Timed only —
# do not gate on non-empty shadow (empty [] kept quiet forever, 2026-08-07).
# Cold-Gateway hydrate takes 60s+; a 20s window let one-shot re-stamp the loop
# on 2026-07-29. With authoritative=True, scan_loop skips IBKR membership polls.
IBKR_SCANNER_WARMUP_QUIET_SEC = 120.0
IBKR_SCANNER_RECONCILE_SEC = 1.0
# Watchdog: warn/resubscribe once when batch age exceeds max(min, mult × cadence).
IBKR_SCANNER_WATCHDOG_MIN_SEC = 90.0
IBKR_SCANNER_WATCHDOG_CADENCE_MULT = 3.0
# Batch qualifyContractsAsync inside snapshot_quotes() — same hang risk as
# scan/snapshot above (see IBKR_L1_QUALIFY_TIMEOUT_SEC's single-symbol note),
# sized higher since discovery batches up to a full scanner page at once.
IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC = 10.0
IBKR_REPRICE_INTERVAL_SEC = 3.0                 # detail-panel cold backstop cadence
# Detail-panel backstop: skip the reqTickersAsync snapshot for a symbol whose
# reqMktData streaming subscription (ibkr/ticks.py) has updated within this
# window — it's already delivering live ticks.
IBKR_DETAIL_STREAM_FRESH_SEC = 8.0
# Kept for UI/docs mirrors; table freshness is now L1-stream driven.
IBKR_TABLE_REPRICE_INTERVAL_SEC = 1.0
# UI / heartbeat: if no successful table price_patch within this window, mark stale.
SCANNER_PRICE_STALE_SEC = 5.0

# ── Active-tab + reserved HOD Level-1 streaming (reqMktData) ──────────────────
# Budget ≈ active tab (≤50) + HOD active set (40) + open ticker reserve, with
# overlap dedupe. Do not stream the whole discovery universe.
IBKR_L1_STREAM_BUDGET = 100                     # Error 101 ceiling; /api/ibkr/status reqMktData_limit
IBKR_L1_STREAM_RESERVE = 5                      # headroom for open ticker / depth peers
IBKR_L1_ACTIVE_TAB_MAX = 50                     # IBKR scanner row cap per tab
IBKR_L1_BATCH_FLUSH_SEC = 0.35                  # coalesce ticks → /ws/scanner patches
IBKR_L1_RECONCILE_SEC = 1.0                     # desired-set reconcile cadence
IBKR_L1_SUBSCRIBE_PACE_SEC = 0.05               # pace subscribe churn (Gateway)
IBKR_L1_TAB_SWITCH_GRACE_SEC = 0.75             # keep prior tab streams briefly on switch
# Qualify/reqMktData without a timeout can hold the ticks subscribe lock for
# minutes when Gateway stalls — HTTP handlers starve → clients timeout →
# CLOSE_WAIT pile-up on :8000. Bound each qualify; cap adds per reconcile.
IBKR_L1_QUALIFY_TIMEOUT_SEC = 4.0
IBKR_L1_MAX_SUBSCRIBE_PER_RECONCILE = 5
# Per-row honesty: tint when last IB tick older than this (liquid symbols).
IBKR_L1_ROW_STALE_SEC = 3.0
# Shortability (tick 236) rides the shared L1 line — see ibkr/ticks_generic.py.
IBKR_SHORTABLE_TICK_WAIT_SEC = 1.8              # max wait for the first 236 tick
# RTVolume (233) rides the shared scanner/detail/HOD line (D-049 / D-020).
# Halted is incoming tick type 49 -> ticker.halted. Do not request generic 49
# (#178). Legal STK generic-tick set lives in ibkr.ticks_generic.
IBKR_HALT_TICK_TYPE = 49
IBKR_L1_GENERIC_TICKS = "233"
# LULD / volatility pause clock (issue #173). First 5m pause, next 5m auction.
# After 10m still halted: no confident forever countdown.
LULD_PAUSE_SEC = 5 * 60
LULD_AUCTION_SEC = 5 * 60
LULD_CONFIDENT_WINDOW_SEC = LULD_PAUSE_SEC + LULD_AUCTION_SEC
# Observed halt_start this many seconds after Nasdaq official start => late.
HALT_LATE_START_SKEW_SEC = 15.0
# Official Nasdaq Trade Halt RSS (not the HTML halt page). Poll <= once/min.
NASDAQ_TRADE_HALT_RSS_URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
NASDAQ_TRADE_HALT_RSS_URL_HTTP = "http://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
NASDAQ_TRADE_HALT_RSS_HALTDATE_PARAM = "haltdate"  # ?feed=tradehalts&haltdate=MM/DD/YYYY
NASDAQ_TRADE_HALT_RSS_NS = "http://www.nasdaqtrader.com/"
NASDAQ_TRADE_HALT_RSS_POLL_SEC = 60.0
NASDAQ_TRADE_HALT_RSS_HTTP_TIMEOUT_SEC = 10.0
NASDAQ_TRADE_HALT_RSS_USER_AGENT = "NovaHaltRss/1.0 (+https://github.com/aaltaay/Nova)"
IBKR_LISTING_FLAGS_TIMEOUT_SEC = 10.0           # sync bridge ceiling for ticker builders

# ── Per-row scanner listing exchange (issue #90) ─────────────────────────────
# IB scan rows rarely carry contract.primaryExchange, so ibkr/exchange_lookup.py
# buys the field with ONE paced qualify round trip per NEW symbol -- cold, and
# off the admit path (ADR 010 name-only admission is untouched). The qualify
# itself reuses IBKR_L1_QUALIFY_TIMEOUT_SEC: no second, unpaced request path.
IBKR_EXCHANGE_LOOKUP_PACE_SEC = 0.25            # gap between consecutive lookups
IBKR_EXCHANGE_LOOKUP_MAX_PENDING = 400          # queue cap; excess waits for a later commit

# ── Strategy: Five Pillars of Stock Selection ─────────────────────────────────
# Signal-only thresholds (see backend/strategy/five_pillars.py). These never place
# orders — they only score a candidate dict (same shape as gapper/gainer cache rows).
# Source: knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md
FIVE_PILLARS_MIN_PRICE = 2.0            # Pillar 1: price floor
FIVE_PILLARS_MAX_PRICE = 20.0           # Pillar 1: price ceiling
FIVE_PILLARS_MIN_CHANGE_PCT = 10.0      # Pillar 2: % up vs prior close (or vs LOD on continuation)
FIVE_PILLARS_MIN_REL_VOLUME = 5.0       # Pillar 3: relative volume multiple
FIVE_PILLARS_MAX_FLOAT_SHARES = 20_000_000  # Pillar 5: float ceiling (shares)

# ── Strategy: Gap and Go setup ────────────────────────────────────────────────
# Codeable rules only — tape-reading / Level 2 nuance is intentionally NOT encoded.
GAP_AND_GO_WINDOW_START_ET = (9, 30)    # session open
GAP_AND_GO_WINDOW_END_ET = (10, 0)      # end of the Gap and Go entry window
GAP_AND_GO_MAX_STOP_DOLLARS = 0.20      # max risk per share (stop distance)
GAP_AND_GO_MIN_PROFIT_LOSS_RATIO = 2.0  # target = entry + risk * this ratio

# ── Bull Flag setup (Phase B) ────────────────────────────────────────────────
# Source: strategy specification — flagpole of green candles, shallow pullback holding the
# 9 EMA, entry on break back above the flagpole high.
BULL_FLAG_LOOKBACK_BARS = 30       # recent 1-min bars scanned for the pattern
BULL_FLAG_MIN_FLAGPOLE_CANDLES = 3  # consecutive green candles forming the pole
BULL_FLAG_MIN_PULLBACK_CANDLES = 2  # consecutive pullback candles forming the flag
BULL_FLAG_EMA_PERIOD = 9
BULL_FLAG_MAX_RETRACE_PCT = 0.50    # pullback must retrace less than this of the pole
BULL_FLAG_MIN_PROFIT_LOSS_RATIO = 2.0

# ── ABCD setup (Phase B) ─────────────────────────────────────────────────────
# Source: strategy specification — A-to-B impulsive move, C pullback holding the 9 EMA,
# entry D on break back above point B.
ABCD_LOOKBACK_BARS = 40            # recent 1-min bars scanned for A/B/C points
ABCD_MIN_AB_MOVE_PCT = 5.0         # minimum % move from A to B to qualify as impulsive
ABCD_EMA_PERIOD = 9
ABCD_MAX_RETRACE_PCT = 0.50        # C must retrace less than this of the A-B move
ABCD_MAX_STOP_DOLLARS = 0.20
ABCD_MIN_PROFIT_LOSS_RATIO = 2.0

# ── Watchlist composite ranking (Phase A) ───────────────────────────────────
# Weighted 0-100 score layered on top of the Five Pillars pass/fail chips.
# Symbols that pass all 5 pillars are always ranked above ones that don't;
# the composite score only breaks ties within each group.
WATCHLIST_WEIGHT_CHANGE_PCT = 0.30
WATCHLIST_WEIGHT_REL_VOLUME = 0.30
WATCHLIST_WEIGHT_FLOAT = 0.20
WATCHLIST_WEIGHT_CATALYST = 0.20
WATCHLIST_CHANGE_PCT_SCORE_CAP = 200.0   # % change that maps to a perfect sub-score
WATCHLIST_REL_VOLUME_SCORE_CAP = 50.0    # RVOL multiple that maps to a perfect sub-score
WATCHLIST_CATALYST_FRESH_MINUTES = 60.0  # headline age considered "fully fresh"
WATCHLIST_CATALYST_STALE_MINUTES = 24 * 60.0  # headline age at which freshness hits 0
WATCHLIST_MAX_ROWS = 60                  # cap on rows returned to the UI

# ── Risk / discipline engine (Phase C) ──────────────────────────────────────
# Source: strategy specification Ch.2, Ch.12; Basics Ch.15. This is a pure state machine — no
# orders are ever placed by backend/strategy/risk.py.
RISK_DAILY_GOAL_DOLLARS = 500.0       # daily profit target; also the daily max-loss walk-away trigger
                                       # NOTE: placeholder default — should become a per-user Settings
                                       # value once the journal/execution phases exist.
RISK_BASE_SHARE_BLOCK = 100           # standard position size, in shares
RISK_QUARTER_SIZE_MULTIPLIER = 0.25   # size used before the profit cushion is reached
RISK_PROFIT_CUSHION_FRACTION = 0.25   # fraction of daily goal that unlocks full size
RISK_SIZE_CUT_LOSS_FRACTION_OF_GOAL = 0.10  # losing this fraction of the daily goal cuts size
RISK_SIZE_CUT_MULTIPLIER = 0.5        # size multiplier applied while in a loss-cut state
RISK_MIN_PROFIT_LOSS_RATIO = 1.0      # absolute floor — never trade below 1:1
RISK_TARGET_PROFIT_LOSS_RATIO = 2.0   # target ratio the setups aim for
RISK_MAX_STOP_DOLLARS = 0.20          # hard ceiling on stop distance for scalps
RISK_PREFERRED_STOP_DOLLARS_LOW = 0.05
RISK_PREFERRED_STOP_DOLLARS_HIGH = 0.10
RISK_MAX_CONSECUTIVE_LOSSES = 3       # walk-away guardrail: 3 losses in a row halts the day
RISK_MAX_GIVEBACK_FRACTION_OF_PEAK = 0.50  # walk-away guardrail: gave back half of today's peak profit
RISK_SESSION_RESET_HOUR_ET = 4        # daily state resets at 4:00 AM ET, mirrors HOD_MOMO_SESSION_RESET_HOUR_ET

# ── Journal (Phase E) ────────────────────────────────────────────────────────
JOURNAL_DB_FILENAME = "journal.db"      # lives under paths.cache_dir(), not git-tracked
JOURNAL_SIGNALS_DEFAULT_LIMIT = 100
JOURNAL_TRADES_DEFAULT_LIMIT = 200
# Activity trail (D-046): journal + ledger join, not a second store
JOURNAL_TRAIL_DEFAULT_LIMIT = 100
# Aligned with Phase I Live-Readiness (≥50 closed / ≥90% adherence).
JOURNAL_MIN_TRADES_FOR_GO_LIVE = 50
JOURNAL_MIN_ADHERENCE_PCT_FOR_GO_LIVE = 90.0
JOURNAL_MOCK_TRADE_COUNT = 12            # rows generated by journal/mock_data.py for UI/logic testing only
# Max acceptable adverse fill vs ticket entry (basis points). Measured in paper first.
SLIPPAGE_MAX_ADVERSE_BPS = 50.0
# P&L calendar (TraderVue-style Reports tab) — days bucketed in America/New_York
JOURNAL_CALENDAR_TIMEZONE = "America/New_York"
JOURNAL_CALENDAR_MIN_YEAR = 2000
JOURNAL_CALENDAR_MAX_YEAR = 2100
# Reports v2 (Phase F) — tag analytics, R-multiples, drawdown
JOURNAL_TAGS_DEFAULT_JSON = "[]"
JOURNAL_TAGS_MAX_PER_TRADE = 20
JOURNAL_IBKR_IMPORT_MAX_ROWS = 500
# Reports file import (D-046 slice 3) -- CSV/JSON only; never Flex/broker API
JOURNAL_IMPORT_MAX_BYTES = 262144
JOURNAL_IMPORT_ACCEPTED_SUFFIXES = (".csv", ".json")

# ── Bracket entry side (ADR 007 broker send) ────────────────────────────────
# Default bracket entry is long; short_entry commands use SELL / journal "short"
# (Phase K / ADR 009). Automation setups remain long-only until a short setup ships.
EXECUTOR_ENTRY_SIDE_IBKR = "BUY"        # default ibkr.orders.OrderSide for bracket entry
EXECUTOR_ENTRY_SIDE_IBKR_SHORT = "SELL"

# ── Level 2 recorder / tape features (Phase F) ──────────────────────────────
# Source: Automation-Strategy-Backbone.md section 3 — tape-reading nuance is
# explicitly NOT automated. backend/l2/ only records,
# scores, and labels; nothing here ever places, modifies, or cancels an order.
# IBKR depth has no historical API, so a recording only covers the window
# AFTER a signal fires, never before it.
L2_DB_FILENAME = "l2.db"               # lives under paths.cache_dir(), not git-tracked
L2_RECORD_WINDOW_SEC = 180.0            # how long to keep snapshotting after a signal fires
L2_SNAPSHOT_INTERVAL_SEC = 2.0          # how often to sample the book during the recording window
L2_ASK_STACKED_RATIO = 1.5              # ask size >= this many times bid size => "seller stacked on the ask"
L2_BID_HEAVY_RATIO = 1.5                # bid size >= this many times ask size => "buyers in control"
L2_PRESSURE_DRYING_LOOKBACK = 5         # snapshots compared to flag "buying pressure drying up"
L2_PRESSURE_DRYING_DROP_FRACTION = 0.30  # bid size must drop by at least this fraction to flag drying up
L2_LABEL_MATCH_TOLERANCE_SEC = 600.0    # max gap between a signal and a journal trade's opened_ts to link them
L2_SPREAD_WIDE_DOLLARS = 0.05           # spread at/above this is flagged "wide" in the UI badge
# Efficient local recorders (hot SQLite window — see Local-Market-Data-Recorders.md)
L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC = 1.0  # book sample rate while a depth session is open
L2_BATCH_SIZE = 64                         # flush L2 snapshot queue after this many pending rows
L2_BATCH_FLUSH_INTERVAL_SEC = 0.25         # or flush at least this often (whichever comes first)
TAPE_BATCH_SIZE = 256                      # flush time & sales queue after this many pending rows
TAPE_BATCH_FLUSH_INTERVAL_SEC = 0.25
L2_RETENTION_DAYS = 14                     # purge l2_snapshots / tape_trades / ended sessions older than this
L2_RETENTION_SWEEP_INTERVAL_SEC = 3600.0   # how often the background retention task runs
L2_RECALL_DEFAULT_WINDOW_SEC = 2.0         # default ±window for point-in-time recall API
TAPE_SOURCE_ALPACA = "alpaca"              # tape_trades.source for Alpaca WS prints
TAPE_SOURCE_IBKR = "ibkr"                 # tape_trades.source for IBKR tick-by-tick prints
IBKR_TAPE_TICK_TYPE = "AllLast"           # tick-by-tick type (AllLast = every print like TWS Time & Sales)
TAPE_UI_MAX_ROWS = 200                    # max rows kept in the frontend Time & Sales panel
L2_SESSION_REASON_SIGNAL = "signal"        # record_sessions.reason when setup signal fires
L2_SESSION_REASON_DEPTH = "depth"          # record_sessions.reason when DepthLadder / depth WS is open

# ── Permanent market-data archive (Nova OS P6–P10) ──────────────────────────
# Hot SQLite capture + local cold compact/restore + optional Cloudflare R2.
# Does NOT bump NOVA_OS_POLICY_VERSION — archive schema is versioned separately.
# Trim of unverified hot data stays blocked until remote verify (P8).
ARCHIVE_SCHEMA_VERSION = "archive-v1-2026-07-15"

# IB's UNSET_DOUBLE is 1.7976931348623157e308 -- an unused LMT/STP price field.
# Any price at or above this floor is that sentinel, never a real price (QA C28).
IB_UNSET_PRICE_FLOOR = 1e300
