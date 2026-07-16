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
/** Invisible placeholder text matching badge height so Level 2 does not jump when heuristics are off. */
export const L2_HEURISTIC_PLACEHOLDER = 'Seller stacked';
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

/** Section title for Alpaca asset / trading flags on the quote card. */
export const QUOTE_BROKER_SECTION_TITLE = 'Listing flags (Alpaca metadata)';

/** Quote card row labels (Alpaca asset fields). */
export const QUOTE_ASSET_LABELS = {
  assetClass: 'Asset class',
  status: 'Asset status',
  tradable: 'Tradable',
  shortable: 'Shortable',
  marginable: 'Marginable',
  fractionable: 'Fractionable',
  easyToBorrow: 'Easy to borrow',
  maintMargin: 'Maint. margin',
  marginLong: 'Margin req. (long)',
  marginShort: 'Margin req. (short)',
  attributes: 'Flags',
  /** Shown beside Flags so the broker grid stays an even cell count (2-column layout). */
  listingFeed: 'Listing feed',
} as const;

/** Display value for listing feed row (Alpaca asset metadata only — not prices/L2). */
export const QUOTE_LISTING_FEED_VALUE = 'Alpaca Assets API (flags only)';

/** Side-panel section that lists which provider powers each ticker surface. */
export const TICKER_DATA_SOURCES_SECTION_TITLE = 'Data sources';
export const TICKER_DATA_SOURCES_SECTION_HINT =
  'Each row shows which API feeds that part of the panel. Switch scanner discovery or Alpaca IEX/SIP in Settings.';

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
  'Alpaca credentials for news, listing metadata, and optional Alpaca scanner mode.';
export const SETTINGS_ALPACA_DATA_FEED_LABEL = 'Alpaca Data Feed';
export const SETTINGS_ALPACA_DATA_FEED_HINT =
  'IEX is free. SIP requires a paid Alpaca data subscription.';

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
// Which source powers gappers/gainers/losers: Alpaca's free screener, or a live
// scan through the user's own IBKR Gateway connection. Reversible any time via
// Settings — see backend/ibkr/discovery.py.
export const DISCOVERY_PROVIDER_DEFAULT = 'alpaca';
/** Human-readable labels for the discovery provider toggle. */
export const DISCOVERY_PROVIDER_LABELS: Record<string, string> = {
  alpaca: 'Alpaca (Free)',
  ibkr: 'Interactive Brokers (Live)',
};

/** Header badge: which provider currently sources scanner rows. */
export const SCANNER_DATA_SOURCE_LABELS: Record<string, string> = {
  alpaca: 'Data: Alpaca',
  ibkr: 'Data: IBKR',
};
export const SCANNER_DATA_SOURCE_TITLES: Record<string, string> = {
  alpaca: 'Scanner data provided by Alpaca Markets (free IEX or SIP feed)',
  ibkr: 'Scanner data provided by your live Interactive Brokers Gateway connection',
};

/** Shown when discovery_provider=ibkr but Gateway is offline (not "no gaps yet"). */
export const EMPTY_IBKR_DISCONNECTED =
  'IB Gateway is not connected — gappers and movers cannot scan. Log into IB Gateway (live, API port 4001), then Nova reconnects automatically.';

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
/** Absolute max width when dragging (px); also clamped so the scanner keeps ~400px. */
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

export const CHART_INDICATORS: { id: ChartIndicatorId; label: string }[] = [
  { id: 'emas', label: 'EMAs' },
  { id: 'vwap', label: 'VWAP' },
  { id: 'rsi', label: 'RSI' },
  { id: 'macd', label: 'MACD' },
];

/** Warrior-style overlays default on (Ross always shows these on the chart). */
export const CHART_DEFAULT_INDICATORS: ChartIndicatorId[] = ['emas', 'vwap'];

export const CHART_OVERLAY_IDS: ChartOverlayId[] = ['emas', 'vwap'];
export const CHART_OSCILLATOR_IDS: ChartOscillatorId[] = ['rsi', 'macd'];

/** Warrior EMA lengths: 9 / 20 / 50 / 200 (BA101 Ch.5 + free ebook). */
export const CHART_EMA_LENGTHS = [9, 20, 50, 200] as const;
export type ChartEmaLength = (typeof CHART_EMA_LENGTHS)[number];

/** Warrior chart overlay colors (BA101 Ch.5 + ebook MA/VWAP legend). */
export const CHART_EMA_COLORS: Record<ChartEmaLength, string> = {
  9: '#9CA3AF',   // grey
  20: '#7DD3FC',  // light blue
  50: '#EF4444',  // red
  200: '#A855F7', // purple
};
export const CHART_VWAP_COLOR = '#F97316'; // orange

export const CHART_INDICATOR_PANE_HEIGHT = 110;
export const CHART_RSI_LENGTH = 14;
export const CHART_MACD_FAST = 12;
export const CHART_MACD_SLOW = 26;
export const CHART_MACD_SIGNAL = 9;

// ── Backend URL ───────────────────────────────────────────────────────────────
// 1) Electron preload may set `window.novaDesktop.apiBase`.
// 2) `main.tsx` sets `window.__NOVA_API_BASE__` after optional fetch of `/config.json`
//    (written at deploy from VITE_API_BASE_URL / NOVA_API_BASE when Vite inlining fails).
// 3) `VITE_API_BASE_URL` at build time (Vite inlining).
// 4) Dev fallback: http://127.0.0.1:8000  (local uvicorn / Electron sidecar).
/** Loopback API used by the Windows Electron desktop shell (mirrors backend). */
export const NOVA_DESKTOP_API_HOST = '127.0.0.1';
export const NOVA_DESKTOP_API_PORT = 8000;
export const NOVA_DESKTOP_API_BASE = `http://${NOVA_DESKTOP_API_HOST}:${NOVA_DESKTOP_API_PORT}`;

declare global {
  interface Window {
    __NOVA_API_BASE__?: string;
    novaDesktop?: {
      isDesktop: boolean;
      apiBase: string;
      getVersion: () => Promise<string>;
      /** Electron IPC: open Stock View in a child BrowserWindow. */
      openStockView?: (url: string) => Promise<boolean>;
    };
  }
}

function readApiBase(): string {
  if (typeof window !== 'undefined') {
    const fromDesktop = window.novaDesktop?.apiBase?.trim();
    if (fromDesktop) return fromDesktop.replace(/\/$/, '');
    const fromBootstrap = window.__NOVA_API_BASE__?.trim();
    if (fromBootstrap) return fromBootstrap.replace(/\/$/, '');
  }
  const fromVite = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  if (fromVite) return fromVite.replace(/\/$/, '');
  return NOVA_DESKTOP_API_BASE;
}

const _rawApiBase: string = readApiBase();
/** REST base, e.g. https://your-service.up.railway.app */
export const API_BASE_URL: string = _rawApiBase;
/** REST API prefix, e.g. https://host/api */
export const API_URL = `${API_BASE_URL}/api`;
/** When true, React/window errors POST to /api/client-errors for blast.log. */
export const CLIENT_ERROR_REPORT_ENABLED = true;
/** WebSocket base derived from API_BASE_URL (https → wss, http → ws). */
export const WS_BASE_URL: string = _rawApiBase
  .replace(/^https:\/\//, 'wss://')
  .replace(/^http:\/\//, 'ws://');

// ── Scanner table columns ─────────────────────────────────────────────────────
// Single source of truth for the columns shown in the Gappers and Movers tables.
// The key must match the ScannerRow field name; the label is the column header text.
// Dense layout: Change combines change_pct/change_abs, Volume combines volume/rel_volume,
// Watch combines watchlist_score (sort key) with the Five Pillars checkmark, and
// Short Int. combines short_interest/short_ratio into stacked dual-value cells
// (see renderCell in components/ScannerTable.tsx). Sort keys stay on the primary field.
// Watch is joined client-side from the Watchlist tab's own scoring (see
// strategy/useWatchlistOverlay.ts) — it does not re-run any scoring logic here.
export const SCANNER_COLUMNS: [string, string][] = [
  ['newest_headline_at',  'News'],
  ['symbol',              'Symbol'],
  ['price',               'Price'],
  ['change_pct',          'Change'],
  ['gap_percent',         'Gap %'],
  ['volume',              'Volume'],
  ['watchlist_score',     'Watch'],
  ['float',               'Float'],
  ['short_interest',      'Short Int.'],
  ['market_cap',          'Mkt Cap'],
];

// ── HOD Momo Scanner ──────────────────────────────────────────────────────────

export interface StrategyMeta {
  id: number;
  name: string;
  color: string;
  audioDefault: boolean;
}

/** Canonical strategy metadata — mirrors backend constants.py HOD_MOMO_STRATEGY_* */
export const STRATEGY_META: StrategyMeta[] = [
  { id: 1,  name: 'Former Momo Stock',                          color: '#FF9100', audioDefault: true  },
  { id: 2,  name: 'Squeeze Alert - 52wk Breakout',              color: '#FFD600', audioDefault: true  },
  { id: 3,  name: 'Low Float - Med Rel Vol',                    color: '#66BB6A', audioDefault: true  },
  { id: 4,  name: 'Low Float - High Rel Vol - Price $20+',      color: '#00BFA5', audioDefault: true  },
  { id: 5,  name: 'Low Float Volatility Hunter',                color: '#FF5252', audioDefault: true  },
  { id: 6,  name: 'Medium Float - High Rel Vol - Price under $20', color: '#B388FF', audioDefault: true },
  { id: 7,  name: 'Low Float - High Rel Vol',                   color: '#00E676', audioDefault: true  },
  { id: 8,  name: 'Medium Float - High Rel Vol - Price $20+',   color: '#448AFF', audioDefault: false },
  { id: 9,  name: 'Medium Float - Med Rel Vol - Price $20+',    color: '#78909C', audioDefault: false },
  { id: 10, name: 'Squeeze Alert - Up 10% in 10min',            color: '#00E5FF', audioDefault: true  },
  { id: 11, name: 'Squeeze Alert - Up 5% in 5min',              color: '#40C4FF', audioDefault: true  },
  { id: 12, name: 'Running Up Alert',                           color: '#FF6E40', audioDefault: true  },
];

/** Warrior Running Up — strategy id 12 (requires_hod=false on the backend). */
export const HOD_MOMO_RUNNING_UP_STRATEGY_ID = 12;

export const STRATEGY_META_MAP: Record<number, StrategyMeta> = Object.fromEntries(
  STRATEGY_META.map(s => [s.id, s]),
);

/** HOD Momo feed columns — mirrors Warrior Daily Rate + 5-min Rel Vol */
export const HOD_MOMO_COLUMNS: [string, string][] = [
  ['time',        'Time'],
  ['symbol',      'Symbol'],
  ['price',       'Price'],
  ['change_pct',  'Change %'],
  ['rvol',        'RVOL (Daily)'],
  ['rvol_5min',   'RVOL (5m)'],
  ['float',       'Float'],
  ['gap_pct',     'Gap %'],
  ['volume',      'Volume'],
  ['strategy',    'Strategy'],
];

/** Visible row window height for the HOD table (~18 dense rows). */
export const HOD_MOMO_VISIBLE_ROWS = 18;
/** Fixed HOD row height used to size the bounded table viewport. */
export const HOD_MOMO_ROW_HEIGHT_PX = 28;
/** Sticky header row height included in the scroll viewport. */
export const HOD_MOMO_HEADER_HEIGHT_PX = 28;
/** Rows mounted initially and added on each distinct bottom reach. */
export const HOD_MOMO_RENDER_BATCH_SIZE = 40;
/** Distance from the table bottom that triggers the next row batch. */
export const HOD_MOMO_LOAD_MORE_THRESHOLD_PX = 24;
/** Batch live alert prepends so App does not re-render on every single fire. */
export const HOD_MOMO_ALERT_BATCH_MS = 150;

/** Empty-state copy when the HOD Momo WS is connected but no alerts have fired yet. */
export const HOD_MOMO_EMPTY_WAITING =
  'Waiting for HOD + momentum alerts (gainers + IBKR volume seeds)…';
export const HOD_MOMO_EMPTY_CONNECTING = 'Connecting to HOD Momo feed…';

/** Poll interval for fail-loud HOD/scanner integrity banner (ms). */
export const HOD_MOMO_INTEGRITY_POLL_MS = 10_000;

/** Default master gate config — mirrors backend MasterGateConfig defaults */
export const DEFAULT_MASTER_GATE = {
  hod_required: true,
  surge_pct: 0.0, // strategies own surge; Warrior does not global-gate 3%/5m
  surge_window_min: 5,
  min_rvol: 2.0,
  premarket_min_rvol: 1.0,
  afterhours_min_rvol: 1.0,
  cooldown_sec: 60.0,
  consolidation_sec: 5.0,
};

// ── Interactive Brokers (mirrors backend/constants.py IBKR_* block) ───────────
/** IB Gateway paper trading port (default when IBKR_LIVE_TRADING_CONFIRMED is not set). */
export const IBKR_PAPER_PORT = 4002;
/** IB Gateway live trading port. */
export const IBKR_LIVE_PORT = 4001;
/** Max simultaneous Level 2 depth streams (IBKR plan cap). */
export const IBKR_MAX_DEPTH_SYMBOLS = 3;
/** Scanner table price refresh target (mirrors backend IBKR_TABLE_REPRICE_INTERVAL_SEC). */
export const IBKR_TABLE_REPRICE_INTERVAL_SEC = 1.0;
/** Mark table prices stale if no successful tick within this many seconds. */
export const SCANNER_PRICE_STALE_SEC = 5.0;
/** Brief flash duration when a table price ticks up/down. */
export const SCANNER_PRICE_FLASH_MS = 400;

// ── Quote Panel (scanner right sidebar) vs Stock View (double-click tab) ─────
/**
 * Delay before a single click selects the Quote Panel. A second click within
 * this window opens Stock View instead (native dblclick is unreliable when the
 * first click re-renders / shifts layout).
 */
export const SYMBOL_DOUBLE_CLICK_MS = 280;
/** Right-hand scanner sidebar that shows quote + fundamentals for the selected symbol. */
export const QUOTE_PANEL_TITLE = 'Quote Panel';
/** Full single-stock page opened by double-click / “Stock View” (detachable tab). */
export const STOCK_VIEW_TITLE = 'Stock View';
/** Button / tooltip copy for opening the detachable Stock View tab. */
export const STOCK_VIEW_OPEN_LABEL = 'Stock View';
export const STOCK_VIEW_OPEN_TITLE =
  'Open Stock View in a new tab (same quote data as the Quote Panel, plus charts and trading)';
/** localStorage key: whether the 2×2 chart grid is collapsed on Stock View. */
export const STOCK_VIEW_CHARTS_COLLAPSED_KEY = 'nova.stockView.chartsCollapsed';
export const STOCK_VIEW_CHARTS_SHOW_LABEL = 'Show charts';
export const STOCK_VIEW_CHARTS_HIDE_LABEL = 'Hide charts';

// ── Full ticker trading page (double-click / Full view) ───────────────────────
/** Quote column width (px) on Stock View when charts are expanded — used until the user drags the resize handle. */
export const TICKER_TRADE_SIDE_WIDTH_PX = 380;
/** Drag-to-resize range (px) for the Stock View quote-panel width. */
export const TICKER_TRADE_SIDE_WIDTH_MIN_PX = 300;
export const TICKER_TRADE_SIDE_WIDTH_MAX_PX = 640;
/** localStorage key: user's saved Stock View quote-panel width (drag-to-resize). */
export const STOCK_VIEW_SIDE_WIDTH_KEY = 'nova.stockView.sideWidthPx';
/** Headlines shown in the trading-page side column before "More". */
export const TICKER_TRADE_SIDE_NEWS_COUNT = 3;
/** Default share quantity prefilled in the Open Position ticket. */
export const TICKER_TRADE_DEFAULT_QTY = 100;
/** Plain-language disclosure under the trading action bar. */
export const TICKER_TRADE_ORDER_DISCLOSURE =
  'Orders go through Interactive Brokers only (paper by default). Alpaca scanning stays read-only.';
/** Depth ladder levels shown in the compact side column (bids + asks each). */
export const TICKER_TRADE_DEPTH_LEVELS = 10;

/**
 * DAS-style Level 2 montage — dark-theme tier palette (price-level groups).
 * Mirrors the classic “each price band gets the next color” montage look.
 * Bid tiers lean green; ask tiers lean red/pink.
 */
export const L2_DAS_TIER_BID: readonly string[] = [
  'rgba(34, 197, 94, 0.55)',
  'rgba(34, 197, 94, 0.38)',
  'rgba(22, 163, 74, 0.28)',
  'rgba(74, 222, 128, 0.22)',
  'rgba(21, 128, 61, 0.20)',
  'rgba(34, 197, 94, 0.14)',
  'rgba(110, 231, 183, 0.12)',
  'rgba(6, 95, 70, 0.18)',
];
export const L2_DAS_TIER_ASK: readonly string[] = [
  'rgba(239, 68, 68, 0.55)',
  'rgba(239, 68, 68, 0.38)',
  'rgba(220, 38, 38, 0.28)',
  'rgba(248, 113, 113, 0.22)',
  'rgba(185, 28, 28, 0.20)',
  'rgba(239, 68, 68, 0.14)',
  'rgba(252, 165, 165, 0.12)',
  'rgba(127, 29, 29, 0.18)',
];
export const L2_DAS_SIZE_BAR_BID = 'rgba(34, 197, 94, 0.35)';
export const L2_DAS_SIZE_BAR_ASK = 'rgba(239, 68, 68, 0.35)';
export const L2_DAS_MM_FALLBACK = '—';
/** IBKR overnight / extended session market-maker id on thin closed-market books. */
export const L2_MM_OVERNIGHT = 'OVERNIGHT';
export const L2_OVERNIGHT_BOOK_HINT =
  'Overnight session book — thin quotes are normal while the regular market is closed.';
export const L2_DAS_HEADERS = {
  bidMm: 'MM',
  bidSize: 'Size',
  bidPrice: 'Bid',
  askPrice: 'Ask',
  askSize: 'Size',
  askMm: 'MM',
} as const;

// ── Time & Sales panel ─────────────────────────────────────────────────────
/** Max rows kept in the TimeSalesPanel (mirrors backend TAPE_UI_MAX_ROWS). */
export const TAPE_UI_MAX_ROWS = 200;
export const TAPE_SECTION_TITLE = 'Time & Sales';
export const TAPE_COL_HEADERS = {
  time: 'Time',
  price: 'Price',
  size: 'Size',
  side: 'Side',
  exchange: 'Exch',
} as const;
/** Labels for aggressor side (not color-only). */
export const TAPE_SIDE_LABELS = {
  ask: 'ASK',
  bid: 'BID',
  between: 'MID',
  unknown: '—',
} as const;
/** Stack L2 | T&S to one column below this width (px). */
export const DEPTH_TAPE_STACK_BREAKPOINT_PX = 560;

/** Universal strategy config zero-defaults (all filters disabled). */
export const DEFAULT_STRATEGY_CONFIG = {
  enabled: true,
  audio: true,
  notes: '',
  min_price: 0,
  max_price: 0,
  min_float: 0,
  max_float: 0,
  min_volume: 0,
  min_rvol: 0,
  max_rvol: 0,
  min_gap_pct: 0,
  max_gap_pct: 0,
  min_change_pct: 0,
  max_change_pct: 0,
  surge_pct: 0,
  surge_window_min: 0,
  surge_method: 'low_to_current' as const,
  proximity_52wk_pct: 0,
  former_momo_list: [] as string[],
  requires_hod: true,
};

/** Party badge next to ticker when earnings date is today (US/Eastern). */
export const EARNINGS_TODAY_PARTY = '🥳';
export const EARNINGS_TODAY_TITLE = 'Earnings today — may be a catalyst';
/** localStorage key: comma-separated symbols forced to show the party badge (testing). */
export const EARNINGS_TODAY_FORCE_STORAGE_KEY = 'nova_force_earnings_today';
/** URL query (?earningsParty=AEHR) also forces badges for testing. */
export const EARNINGS_TODAY_FORCE_QUERY = 'earningsParty';
export const EARNINGS_TODAY_BATCH_MS = 400;
export const EARNINGS_TODAY_BATCH_MAX = 25;

/** HOD Strategies filter dropdown — tall enough to show most strategies without scroll. */
export const HOD_STRATEGY_FILTER_MAX_HEIGHT_PX = 520;
