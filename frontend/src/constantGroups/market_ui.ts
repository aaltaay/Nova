/**
 * Authoritative UI policy and thresholds for Nova.
 * Keep numeric rules in sync with `backend/constants.py` where they overlap.
 */

// ── Market cap tiers (USD) ─────────────────────────────────────────────────
export const SMALL_CAP_MIN =   300_000_000;   //  $300 M
export const SMALL_CAP_MAX = 2_000_000_000;   //   $2 B
export const MID_CAP_MIN   = 2_000_000_000;   //   $2 B
export const MID_CAP_MAX   = 10_000_000_000;  //  $10 B
export const LARGE_CAP_MIN = 10_000_000_000;  //  $10 B

// ── News flame thresholds (hours) ──────────────────────────────────────────
export const NEWS_FLAME_HOT_HOURS  =  2;   // red badge    (0 –  2 h)
export const NEWS_FLAME_WARM_HOURS = 12;   // orange badge (2 – 12 h)
export const NEWS_FLAME_MAX_HOURS  = 24;   // yellow badge (12 – 24 h); hide above this

// ── News impact decision layer (mirrors backend/constants.py NEWS_IMPACT_*) ─
/** Display labels for impact_class — keep in sync with backend IMPACT_CLASSES. */
export const NEWS_IMPACT_CLASS_LABELS: Record<string, string> = {
  moved_price: 'Bump due to news',
  attention_only: 'Attention only',
  no_effect: 'No effect on ticker',
  insufficient_data: 'Insufficient data',
};

export const NEWS_IMPACT_CLASS_TOOLTIPS: Record<string, string> = {
  moved_price:
    'Fresh/aging headline plus a mild or strong price move — rules attribute the bump to news.',
  attention_only:
    'News is present and relative volume is elevated, but price has not moved enough to count as a reaction.',
  no_effect:
    'News is present (or expired) but rules do not attribute a meaningful ticker move to it.',
  insufficient_data:
    'Missing articles and/or market context needed to classify impact.',
};

export const NEWS_IMPACT_FACTOR_TOOLTIPS = {
  age: 'How old the newest headline is. Tunables: NEWS_IMPACT_FRESH/AGING/STALE_HOURS in backend/constants.py.',
  source: 'Credibility tier from source name/URL keywords (official > major > secondary > unknown).',
  price: 'Price reaction from |gap%| vs NEWS_IMPACT_STRONG_MOVE_PCT / MILD_MOVE_PCT.',
  attention: 'Relative volume vs NEWS_IMPACT_ATTENTION_RVOL — elevated means an attention spike.',
  l2: 'Level 2 reaction from live book imbalance / bid-heavy (or insufficient_data if no book).',
  sentiment: 'Local FinBERT read of the headline text (positive/negative/neutral). Informational only — does not change impact_class.',
  lexicon: 'Independent Loughran-McDonald financial word-list read of the headline. Informational only — does not change impact_class.',
  confidence: 'Rules-first score clamped by NEWS_IMPACT_CONFIDENCE_FLOOR/CEILING — not a black-box model.',
  ai: 'Lincoln AI narrative. Opt-in via LINCOLN_AI_ENABLED + OPENAI_API_KEY (backend/news/ai_reasoning.py) — null when disabled.',
};

// ── Strategy / Watchlist tab (mirrors backend constants.py WATCHLIST_*) ────
export const WATCHLIST_POLL_INTERVAL_MS = 3000;
/** Composite score column headers, in display order. */
export const WATCHLIST_SUBSCORE_LABELS: Record<string, string> = {
  change_pct: '% Chg',
  relative_volume: 'RVOL',
  float: 'Float',
  catalyst: 'News',
};

/** Hover tooltips explaining each composite sub-score, 0-100 scale. */
export const WATCHLIST_SUBSCORE_TOOLTIPS: Record<string, string> = {
  change_pct: "0-100 score from today's % price change — bigger moves score higher, capped at WATCHLIST_CHANGE_PCT_SCORE_CAP.",
  relative_volume: "0-100 score from volume vs. this symbol's own average — higher relative volume scores higher, capped at WATCHLIST_REL_VOLUME_SCORE_CAP.",
  float: '0-100 score for a tighter (smaller) share float — tighter floats move faster and score higher.',
  catalyst: "0-100 score for how fresh the news catalyst is — a headline within the last few minutes scores highest, fading to 0 once it's stale.",
};

/** Side-panel strip under News Headline — mirrors Watchlist tab columns without Symbol. */
export const TICKER_WATCHLIST_STRIP_TITLE = 'Watchlist';
export const TICKER_WATCHLIST_STRIP_EMPTY = 'Not ranked on the current watchlist.';

/** Display labels for the setup-signal stream (mirrors backend SETUP_NAMES). */
export const SETUP_LABELS: Record<string, string> = {
  gap_and_go: 'Gap and Go',
  bull_flag: 'Bull Flag',
  abcd: 'ABCD',
};

/** Journal panel poll interval — metrics/signals change slowly, no need for the watchlist's cadence. */
export const JOURNAL_POLL_INTERVAL_MS = 15000;
export const JOURNAL_RECENT_SIGNALS_LIMIT = 25;
/** Mirrors backend JOURNAL_CALENDAR_TIMEZONE — calendar days are America/New_York. */
export const JOURNAL_CALENDAR_TIMEZONE = 'America/New_York';

/** Executor (Phase D) status poll interval — armed state and open positions can change
 * quickly once a bracket fills, so this polls faster than the Journal panel. */
export const EXECUTOR_POLL_INTERVAL_MS = 5000;

// ── Nova OS Decision UX (mirrors backend/constants.py NOVA_OS_*) ────────────
/** Poll interval for DecisionPanel watchlist/symbol decide fetches. */
export const NOVA_OS_DECIDE_POLL_INTERVAL_MS = 5000;
/** Faster poll for Trader Nova OS dock tab (single symbol, while mounted). */
export const NOVA_OS_TRADER_DECIDE_POLL_MS = 2000;

/** Header toggle + banner for isolated sample-data route (?view=sample). */
export const SAMPLE_DATA_SWITCH_LABEL = 'Sample data';
export const SAMPLE_DATA_BANNER =
  'Sample data route — fixtures only. Live scanner, HOD, watchlist, and IBKR feeds are not connected.';
/** Education strip under Trader Nova OS brain (rules brain, not chat AI). */
export const NOVA_OS_TRADER_BRAIN_DISCLOSURE =
  'Nova OS rules brain (not chat AI). You are watching live ratings. Signal-only — nothing places from Trader. Like the calls? Watchlist → Automation → Confirm / Auto Paper.';
/** Exit context when Trader shows an open position for the symbol. */
export const NOVA_OS_TRADER_EXIT_NOTE =
  'exits use stop/Flatten/hotkeys, not a sell decide().';
/** Poll interval for the global Nova OS event-attention feed (GET /api/nova-os/events). */
export const NOVA_OS_EVENT_ATTENTION_POLL_INTERVAL_MS = 5000;
/** How many recent events to fetch per poll — must comfortably exceed the
 * number of receipts one poll interval could produce so nothing is missed. */
export const NOVA_OS_EVENT_ATTENTION_POLL_LIMIT = 25;
/** Default watchlist batch size for GET /api/nova-os/decide (mirrors NOVA_OS_DECIDE_DEFAULT_LIMIT). */
export const NOVA_OS_DECIDE_DEFAULT_LIMIT = 4;
/** localStorage key for the muteable attention-sound preference. */
export const NOVA_OS_ATTENTION_MUTE_STORAGE_KEY = 'nova_os_attention_muted';
/** When true, attention cues are silent by default until the user unmutes. */
export const NOVA_OS_ATTENTION_MUTED_DEFAULT = false;
/** Short labels for BUY | WAIT | NO_BUY verdict chips. */
export const NOVA_OS_DECISION_LABELS: Record<string, string> = {
  BUY: 'BUY',
  WAIT: 'WAIT',
  NO_BUY: 'NO BUY',
};
/** Plain-language subtitles for the attention strip event kinds. */
export const NOVA_OS_ATTENTION_COPY: Record<string, string> = {
  decision_buy: 'Nova OS: BUY decision — review the ticket (signal only; nothing placed).',
  decision_wait: 'Nova OS: WAIT — catalyst or soft gate held the entry.',
  decision_no_buy: 'Nova OS: NO BUY — see the first failing gate.',
  mode_reset: 'Automation reset to Signal — nothing will place until you raise the mode.',
  risk_halt: 'Risk halt — new entries blocked for the session.',
  staged: 'Ticket staged — Approve before the countdown expires to place the paper bracket.',
  expired: 'Staged ticket expired unapproved — nothing was placed.',
  fill: 'Paper bracket placed — entry order working on IBKR.',
  stop: 'Position closed — see Journal for exit price and P&L.',
  kill: 'Kill switch tripped — automation forced to Signal.',
  archive_fail: 'Archive upload failed for a prior day — see Archive health.',
};

/** Mirrors backend NOVA_OS_FLATTEN_CONFIRM_TOKEN — typed confirm for flatten. */
export const NOVA_OS_FLATTEN_CONFIRM_TOKEN = 'FLATTEN';
/** Mirrors backend NOVA_OS_CONFIRM_TIMEOUT_SEC (display only). */
export const NOVA_OS_CONFIRM_TIMEOUT_SEC = 45;

/** Level 2 heuristic badge thresholds (Phase F). Mirrors backend/constants.py
 * L2_ASK_STACKED_RATIO / L2_BID_HEAVY_RATIO / L2_SPREAD_WIDE_DOLLARS — kept in
 * sync manually since these badges are single-snapshot-only display heuristics
 * on the live DepthLadder (the backend also computes a fuller feature series,
 * including a multi-snapshot "drying up" trend, for the recorded dataset in
 * l2/features.py). Never fed into automation — see Automation-Strategy-Backbone.md #3. */
export const L2_ASK_STACKED_RATIO = 1.5;
export const L2_BID_HEAVY_RATIO = 1.5;
export const L2_SPREAD_WIDE_DOLLARS = 0.05;
/** Idle label when no stack/spread heuristic fires — keeps the L2 badge row stable. */
export const L2_HEURISTIC_IDLE_LABEL = 'No stack';
/** @deprecated Use L2_HEURISTIC_IDLE_LABEL — kept for any leftover imports. */
export const L2_HEURISTIC_PLACEHOLDER = L2_HEURISTIC_IDLE_LABEL;
export const L2_HEURISTIC_ASK_LABEL = 'Seller stacked';
export const L2_HEURISTIC_BID_LABEL = 'Bid heavy';
export const L2_HEURISTIC_SPREAD_LABEL = 'Wide spread';
export const L2_HEURISTIC_TITLE =
  'Rule-of-thumb read of resting size. Display-only — never feeds the executor.';

// ── Relative volume ────────────────────────────────────────────────────────
export const REL_VOLUME_HIGH = 2;   // highlight threshold (≥ 2×)
/** Trading days used for avg daily volume / RVOL denominator (mirror backend RVOL_LOOKBACK_DAYS). */
export const RVOL_LOOKBACK_DAYS = 30;

/** Visible title at the top of the side-panel quote card (for orientation in UI and discussion). */
export const QUOTE_CARD_TITLE = 'Stock quote';

/** Side panel quote card — row label for average volume used in RVOL. */
export const QUOTE_AVG_VOLUME_LABEL = `Avg volume (${RVOL_LOOKBACK_DAYS}d)`;

/** Section title for dual-broker listing flags on the quote card. */
export const QUOTE_BROKER_SECTION_TITLE = 'Listing flags (compare brokers)';
export const QUOTE_LISTING_ALPACA_TITLE = 'Alpaca';
export const QUOTE_LISTING_IBKR_TITLE = 'IBKR';
export const QUOTE_LISTING_COMPARE_HINT =
  'Side-by-side metadata only — never merged. Alpaca shortable/ETB ≠ IBKR locate.';

/** Quote card row labels (Alpaca asset fields). */
export const QUOTE_ASSET_LABELS = {
  assetClass: 'Asset class',
  status: 'Asset status',
  tradable: 'Tradable',
  shortable: 'Shortable',
  shortType: 'Short type',
  marginable: 'Marginable',
  fractionable: 'Fractionable',
  easyToBorrow: 'Easy to borrow',
  maintMargin: 'Maint. margin',
  marginLong: 'Margin req. (long)',
  marginShort: 'Margin req. (short)',
  attributes: 'Flags',
  /** Shown beside Flags so the broker grid stays an even cell count (2-column layout). */
  listingFeed: 'Listing feed',
  qualified: 'Qualified',
  shortableShares: 'Shortable shares',
  stockType: 'Stock type',
  longName: 'Name',
} as const;

/** Display value for listing feed row (Alpaca asset metadata only — not prices/L2). */
export const QUOTE_LISTING_FEED_VALUE = 'Alpaca Assets API (flags only)';

/** Scanner Volume column: live volume is IBKR; RVOL denom badge is Alpaca avg. */
export const SCANNER_VOLUME_COLUMN_LABEL = 'Volume · RVOL';
export const SCANNER_RVOL_ALPACA_BADGE = 'Alpaca avg';
export const SCANNER_RVOL_ALPACA_TITLE =
  'Live volume is IBKR L1. Relative volume uses Alpaca daily-bar average (aux) — not IBKR consolidated volume. Thin names can look wrong; study vs tape before trusting.';
export const QUOTE_RVOL_DAILY_LABEL = 'Rel vol (Alpaca avg)';
export const QUOTE_RVOL_DAILY_TITLE = SCANNER_RVOL_ALPACA_TITLE;

/** Header aux API chips (not the live price feed — Gateway/Feed stay separate). */
export const HEADER_INTEGRATION_CHIP_ORDER = [
  'alpaca',
  'openai',
  'yfinance',
  'archive',
] as const;
export const HEADER_INTEGRATION_CHIP_LABELS: Record<string, string> = {
  // Under IBKR discovery this is news/listing aux — not the live scanner feed.
  alpaca: 'News',
  openai: 'OpenAI',
  yfinance: 'yfinance',
  archive: 'Archive',
  ibkr: 'IBKR',
};

/** Side-panel section that lists which provider powers each ticker surface. */
export const TICKER_DATA_SOURCES_SECTION_TITLE = 'Data sources';
export const TICKER_DATA_SOURCES_SECTION_HINT =
  'Scanner, quote, chart, L2, and Time & Sales are IBKR. Alpaca appears only for listing flags / RVOL avg (aux).';

/** Suffix on the Level 2 section title so depth is never confused with Alpaca listing flags. */
export const TICKER_L2_SOURCE_LABEL = 'IBKR';

// ── Data feed (mirrors backend DATA_FEED_DEFAULT / DATA_FEED_OPTIONS) ───────
export const DATA_FEED_DEFAULT = 'iex';
/** Human-readable labels for the Alpaca data feed tiers. */
export const DATA_FEED_LABELS: Record<string, string> = {
  iex: 'IEX (Free)',
  sip: 'SIP (Paid)',
};
/** Settings form labels — provider-prefixed so multiple API key groups stay clear. */
export const SETTINGS_ALPACA_API_KEY_LABEL = 'Alpaca API Key ID';
export const SETTINGS_ALPACA_API_SECRET_LABEL = 'Alpaca API Secret Key';
export const SETTINGS_ALPACA_BASE_URL_LABEL = 'Alpaca Base URL';
export const SETTINGS_ALPACA_API_KEY_PLACEHOLDER = 'APCA_API_KEY_ID';
export const SETTINGS_ALPACA_API_SECRET_PLACEHOLDER = 'APCA_API_SECRET_KEY';
export const SETTINGS_ALPACA_SECTION_HINT =
  'Alpaca credentials for news and listing metadata only — not the live scanner.';
export const SETTINGS_ALPACA_DATA_FEED_LABEL = 'Alpaca Data Feed (aux)';
export const SETTINGS_ALPACA_DATA_FEED_HINT =
  'News/listing aux only — not live scanner prices. IEX is free; SIP needs a paid Alpaca plan.';

// ── Dashboard tab ─────────────────────────────────────────────────────────────
/** Max rows shown per section on the Dashboard snapshot view. */
export const DASHBOARD_TOP_N = 50;

// ── Exchange filter (Dashboard + scanner tabs) ────────────────────────────────
/** All exchanges that can appear in scanner rows. Displayed in order in the dropdown. */
export const SCANNER_EXCHANGE_OPTIONS = ['NASDAQ', 'NYSE', 'AMEX', 'ARCA', 'BATS', 'IEX', 'CBOE'] as const;
/** Exchanges selected by default (NASDAQ only). */
export const SCANNER_EXCHANGE_DEFAULTS: string[] = ['NASDAQ'];
/** localStorage key used by useExchangeFilter. */
export const SCANNER_EXCHANGE_STORAGE_KEY = 'nova_exchange_filter_v1';

/** localStorage key: module id → visible (Phase 4 Modules menu). */
export const MODULE_VISIBILITY_STORAGE_KEY = 'nova_module_visibility_v1';

/** localStorage key: versioned workspace layout (Phase 5). */
export const LAYOUT_STORAGE_KEY = 'nova_workspace_layout_v1';
/** Schema version written into the layout JSON blob. */
export const LAYOUT_SCHEMA_VERSION = 1;

/** Scanner / HOD table text size — user preference (localStorage). */
export const SCANNER_TABLE_DENSITY_STORAGE_KEY = 'nova_scanner_table_density_v2';
export type ScannerTableDensity = 'compact' | 'medium' | 'large' | 'xlarge';
/** Default Large (1rem) for readable scanner tables out of the box. */
export const SCANNER_TABLE_DENSITY_DEFAULT: ScannerTableDensity = 'large';
/** CSS root font-size (rem) per density — drives `--scanner-table-fs`. */
export const SCANNER_TABLE_DENSITY_REM: Record<ScannerTableDensity, string> = {
  compact: '0.75rem',
  medium: '0.875rem',
  large: '1rem',
  xlarge: '1.125rem',
};
export const SCANNER_TABLE_DENSITY_LABELS: Record<ScannerTableDensity, string> = {
  compact: 'Compact',
  medium: 'Medium',
  large: 'Large',
  xlarge: 'Extra large',
};
export const SCANNER_TABLE_DENSITY_OPTIONS: ScannerTableDensity[] = [
  'compact',
  'medium',
  'large',
  'xlarge',
];

// ── Discovery provider (mirrors backend DISCOVERY_PROVIDER_DEFAULT / _OPTIONS) ─
// Product lock: IBKR is the only scanner discovery source. Alpaca remains for
// news / listing metadata only — see backend/ibkr/discovery.py.
export const DISCOVERY_PROVIDER_DEFAULT = 'ibkr';
/** Human-readable labels (ibkr is the only product option). */
export const DISCOVERY_PROVIDER_LABELS: Record<string, string> = {
  ibkr: 'Interactive Brokers (Gateway)',
};

/** Header badge: which provider currently sources scanner rows. */
export const SCANNER_DATA_SOURCE_LABELS: Record<string, string> = {
  ibkr: 'Data: IBKR',
};
export const SCANNER_DATA_SOURCE_TITLES: Record<string, string> = {
  ibkr: 'Scanner data provided by your live Interactive Brokers Gateway connection',
};

/** Shown when discovery_provider=ibkr but Gateway is offline (not "no gaps yet"). */
export const EMPTY_IBKR_DISCONNECTED =
  'IB Gateway is not connected — gappers and movers cannot scan. Log into IB Gateway with the API enabled on the port Nova targets, then Nova reconnects automatically.';

/** Mode-aware empty copy — prefer over EMPTY_IBKR_DISCONNECTED when gateway_mode is known. */
export const EMPTY_IBKR_DISCONNECTED_PAPER =
  'IB Gateway is not connected — gappers and movers cannot scan. Log into IB Gateway (paper, API port 4002), then Nova reconnects automatically.';
export const EMPTY_IBKR_DISCONNECTED_LIVE =
  'IB Gateway is not connected — gappers and movers cannot scan. Log into IB Gateway (live, API port 4001), then Nova reconnects automatically.';

/** Stock View header — disconnected without a port-mismatch hint. */
export const STOCK_VIEW_DISCONNECTED_LABEL = 'Disconnected';

/** Port-mismatch CTA when preferred port is down but the other is listening. */
export const STOCK_VIEW_DISCONNECT_HINT_PAPER_LIVE_UP =
  'Nova targets Paper (4002) — not listening. Live (4001) is up — switch to Live?';
export const STOCK_VIEW_DISCONNECT_HINT_LIVE_PAPER_UP =
  'Nova targets Live (4001) — not listening. Paper (4002) is up — switch to Paper?';
export const STOCK_VIEW_DISCONNECT_HINT_BOTH_DOWN =
  'Gateway ports 4001/4002 not listening — start IB Gateway and log in.';
export const STOCK_VIEW_DISCONNECT_HINT_PORT_OPEN =
  'Gateway port is open but Nova is not connected — check clientId / TrustedIPs / login.';

/** Capsule error when POST /api/ibkr/gateway-mode is missing (stale API process). */
export const GATEWAY_MODE_API_RESTART_HINT =
  'Restart Nova API (route missing), then try switching again.';

/** Header Gateway chip tooltip — double-click launches/focuses the desktop app. */
export const HEADER_GATEWAY_LAUNCH_HINT =
  'Double-click to open or focus IB Gateway. Complete login + IBKR Mobile 2FA if prompted — Nova reconnects when the API port opens.';

/** Header Gateway chip — paper vs live session (must stay visible; never omit). */
export const HEADER_GATEWAY_MODE_PAPER = 'PAPER';
export const HEADER_GATEWAY_MODE_LIVE = 'LIVE';
export const HEADER_GATEWAY_TITLE_PAPER =
  'IBKR session: PAPER — paper account / paper Gateway port. Not live money.';
export const HEADER_GATEWAY_TITLE_LIVE =
  'IBKR session: LIVE — real account Gateway. Market data and orders use the live port; spend still gated by IBKR_ORDERS_ENABLED + live confirm.';
export const HEADER_GATEWAY_TITLE_UNKNOWN =
  'IBKR session mode unknown — check Trading /api/ibkr/status (mode / gateway_mode).';

/** Human-readable labels for Alpaca `attributes` tokens (unknown keys shown as-is). */
export const ALPACA_ASSET_ATTRIBUTE_LABELS: Record<string, string> = {
  overnight_halted: 'Overnight session halted',
  overnight_tradable: 'Overnight tradable',
  has_options: 'Listed options',
  fractional_eh_enabled: 'Fractional extended hours',
};

// ── Minimum price filter (mirror backend SCANNER_MIN_PRICE) ─────────────────
export const SCANNER_MIN_PRICE = 0.50;  // exclude any stock priced below $0.50 (gainers + gappers)

// Scanner universe: mirror backend SCAN_REQUIRE_TRADABLE / NOVA_SCAN_REQUIRE_TRADABLE (backend-only toggle).

// ── Gapper filter (mirror backend GAPPER_MIN_GAP_PCT) ───────────────────────
export const GAPPER_MIN_GAP_PCT = 10;   // minimum gap % vs prior close to show as a gapper

// ── US equity session clock (America/New_York) ───────────────────────────────
// Mirror of backend/constants_scanner.py SESSION_* — used by chart session
// highlighting (frontend/src/chart/sessionHighlight.ts). Keep in sync.
/** Premarket open 04:00 ET — minutes from midnight. */
export const SESSION_PREMARKET_START_MIN_ET = 4 * 60;
/** Regular-session open 09:30 ET. */
export const SESSION_RTH_OPEN_MIN_ET = 9 * 60 + 30;
/** Regular-session close / after-hours start 16:00 ET. */
export const SESSION_RTH_CLOSE_MIN_ET = 16 * 60;
/** After-hours end 20:00 ET. */
export const SESSION_AFTERHOURS_END_MIN_ET = 20 * 60;

/** Background tint behind candles for each session (intraday charts only). */
export const CHART_SESSION_COLORS = {
  premarket: 'rgba(245, 158, 11, 0.10)',
  rth: 'rgba(16, 185, 129, 0.05)',
  afterhours: 'rgba(59, 130, 246, 0.10)',
  closed: 'rgba(0, 0, 0, 0.18)',
} as const;

export const CHART_SESSION_LEGEND = [
  { id: 'premarket', label: 'Premarket', color: CHART_SESSION_COLORS.premarket },
  { id: 'rth', label: 'RTH', color: CHART_SESSION_COLORS.rth },
  { id: 'afterhours', label: 'After-hours', color: CHART_SESSION_COLORS.afterhours },
] as const;

// ── Ticker chart ─────────────────────────────────────────────────────────────
// Mirrors backend CHART_TIMEFRAMES / CHART_DEFAULT_TIMEFRAME in constants.py.
export interface ChartTimeframe {
  /** Alpaca API timeframe string (also used as query param) */
  id: string;
  /** Short label shown on the timeframe tab buttons */
  label: string;
}
export const CHART_TIMEFRAMES: ChartTimeframe[] = [
  { id: '1Min',   label: '1m'  },
  { id: '5Min',   label: '5m'  },
  { id: '15Min',  label: '15m' },
  { id: '30Min',  label: '30m' },
  { id: '1Hour',  label: '1H'  },
  { id: '4Hour',  label: '4H'  },
  { id: '1Day',   label: '1D'  },
  { id: '1Week',  label: '1W'  },
  { id: '1Month', label: '1M'  },
];
export const CHART_DEFAULT_TIMEFRAME = '1Min';
export const CHART_CARD_TITLE = 'Price Chart';
/** Chart body height (px) in the widened side panel. */
export const CHART_HEIGHT_PANEL = 320;
/** Chart body height (px) on the full ticker detail page (single chart / legacy). */
export const CHART_HEIGHT_PAGE = 440;
/** Minimum chart body height (px) per 2×2 grid cell — cells stretch to fill ~80% of the trading viewport. */
export const CHART_HEIGHT_GRID = 180;
/**
 * Full trading page (double-click) 2×2 panels.
 * Fourth panel is 15Min temporarily — Alpaca has no historical sub-minute;
 * a live 10-second tape panel will replace/add later.
 */
export const CHART_GRID_PANELS: { id: string; label: string; note?: string }[] = [
  { id: '1Min', label: '1-Minute' },
  { id: '5Min', label: '5-Minute' },
  { id: '1Day', label: 'Full Day' },
  {
    id: '15Min',
    label: '15-Minute',
    note: 'Temp stand-in — 10s live tape coming later',
  },
];
/** Side panel default width (px) on wide viewports — room for quote | chart | fundamentals. */
export const SIDE_PANEL_WIDTH_PX = 820;
/** Minimum width when dragging the splitter (px). */
export const SIDE_PANEL_MIN_WIDTH_PX = 360;
/** Minimum dashboard width retained for scanner columns before the side panel stacks. */
export const SCANNER_MIN_REMAINING_PX = 830;
/** Absolute max width when dragging (px); also clamped so the scanner stays usable. */
export const SIDE_PANEL_MAX_WIDTH_PX = 1400;
/** Side panel max share of viewport width used as an upper clamp while resizing. */
export const SIDE_PANEL_MAX_VIEWPORT_PCT = 70;
/** localStorage key for the user-resized side panel width. */
export const SIDE_PANEL_WIDTH_STORAGE_KEY = 'nova_side_panel_width_v1';
/** Below this viewport width, side panel stacks under the scanner (full width). */
export const SIDE_PANEL_STACK_BREAKPOINT_PX = 1100;
/** When Alpaca returns zero bars (weekend / thin symbols), synthesize this many
 * candles so the chart + drawing tools remain usable for verification. */
export const CHART_MOCK_BAR_COUNT = 48;
export const CHART_MOCK_BASE_PRICE = 10;
export const CHART_MOCK_DATA_LABEL = 'Demo candles (no live bars for this timeframe)';
/** Client abort for /bars so "Loading…" cannot spin past the IBKR historical budget. */
export const CHART_BARS_FETCH_TIMEOUT_MS = 25_000;
export const CHART_REFETCH_SEC: Record<string, number> = {
  // Live forming candle comes from WS ticks; poll is reconciliation only.
  '1Min': 30,
  '5Min': 30,
  '15Min': 45,
  '30Min': 60,
  '1Hour': 120,
  '4Hour': 180,
};

/**
 * Chart indicator toggles — computed via lightweight-charts-indicators (not hand-rolled).
 * `emas` / `vwap` are price-pane overlays; `rsi` / `macd` are oscillator panes.
 */
export type ChartIndicatorId = 'emas' | 'vwap' | 'rsi' | 'macd';
export type ChartOverlayId = 'emas' | 'vwap';
export type ChartOscillatorId = 'rsi' | 'macd';

