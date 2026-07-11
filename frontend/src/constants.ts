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
  confidence: 'Rules-first score clamped by NEWS_IMPACT_CONFIDENCE_FLOOR/CEILING — not a black-box model.',
  ai: 'Lincoln AI narrative slot. Always pending/null until the AI reasoning hook is wired.',
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

/** Level 2 heuristic badge thresholds (Phase F). Mirrors backend/constants.py
 * L2_ASK_STACKED_RATIO / L2_BID_HEAVY_RATIO / L2_SPREAD_WIDE_DOLLARS — kept in
 * sync manually since these badges are single-snapshot-only display heuristics
 * on the live DepthLadder (the backend also computes a fuller feature series,
 * including a multi-snapshot "drying up" trend, for the recorded dataset in
 * l2/features.py). Never fed into automation — see Automation-Strategy-Backbone.md #3. */
export const L2_ASK_STACKED_RATIO = 1.5;
export const L2_BID_HEAVY_RATIO = 1.5;
export const L2_SPREAD_WIDE_DOLLARS = 0.05;

// ── Relative volume ────────────────────────────────────────────────────────
export const REL_VOLUME_HIGH = 2;   // highlight threshold (≥ 2×)
/** Trading days used for avg daily volume / RVOL denominator (mirror backend RVOL_LOOKBACK_DAYS). */
export const RVOL_LOOKBACK_DAYS = 30;

/** Visible title at the top of the side-panel quote card (for orientation in UI and discussion). */
export const QUOTE_CARD_TITLE = 'Stock quote';

/** Side panel quote card — row label for average volume used in RVOL. */
export const QUOTE_AVG_VOLUME_LABEL = `Avg volume (${RVOL_LOOKBACK_DAYS}d)`;

/** Section title for Alpaca asset / trading flags on the quote card. */
export const QUOTE_BROKER_SECTION_TITLE = 'Broker listing (Alpaca)';

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

/** Display value for listing feed row (source of asset metadata on the quote card). */
export const QUOTE_LISTING_FEED_VALUE = 'Alpaca Trading API';

// ── Data feed (mirrors backend DATA_FEED_DEFAULT / DATA_FEED_OPTIONS) ───────
export const DATA_FEED_DEFAULT = 'iex';
/** Human-readable labels for the Alpaca data feed tiers. */
export const DATA_FEED_LABELS: Record<string, string> = {
  iex: 'IEX (Free)',
  sip: 'SIP (Paid)',
};

/** Header badge: scanner rows come from Alpaca (not IBKR). */
export const SCANNER_DATA_SOURCE_LABEL = 'Data: Alpaca';
export const SCANNER_DATA_SOURCE_TITLE =
  'Scanner data provided by Alpaca Markets (free IEX or SIP feed)';

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

// ── News Catalysts tab ────────────────────────────────────────────────────────
// Label shown on the experimental Catalysts tab badge
export const CATALYSTS_EXPERIMENTAL_LABEL = 'Experimental';

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
export const CHART_DEFAULT_TIMEFRAME = '5Min';
export const CHART_CARD_TITLE = 'Price Chart';
/** Chart body height (px) in the widened side panel. */
export const CHART_HEIGHT_PANEL = 320;
/** Chart body height (px) on the full ticker detail page (single chart / legacy). */
export const CHART_HEIGHT_PAGE = 440;
/** Chart body height (px) for each cell in the 2×2 trading-page grid. */
export const CHART_HEIGHT_GRID = 260;
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
/** Side panel width (px) on wide viewports — room for quote | chart | fundamentals. */
export const SIDE_PANEL_WIDTH_PX = 820;
/** Side panel max share of viewport width (CSS max-width: Nvw). */
export const SIDE_PANEL_MAX_VIEWPORT_PCT = 55;
/** Below this viewport width, side panel stacks under the scanner (full width). */
export const SIDE_PANEL_STACK_BREAKPOINT_PX = 1100;
/** When Alpaca returns zero bars (weekend / thin symbols), synthesize this many
 * candles so the chart + drawing tools remain usable for verification. */
export const CHART_MOCK_BAR_COUNT = 48;
export const CHART_MOCK_BASE_PRICE = 10;
export const CHART_MOCK_DATA_LABEL = 'Demo candles (no live bars for this timeframe)';

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
/** WebSocket base derived from API_BASE_URL (https → wss, http → ws). */
export const WS_BASE_URL: string = _rawApiBase
  .replace(/^https:\/\//, 'wss://')
  .replace(/^http:\/\//, 'ws://');

// ── Scanner table columns ─────────────────────────────────────────────────────
// Single source of truth for the columns shown in the Gappers and Movers tables.
// The key must match the ScannerRow field name; the label is the column header text.
export const SCANNER_COLUMNS: [string, string][] = [
  ['symbol',          'Symbol'],
  ['price',           'Price'],
  ['change_pct',      'Change %'],
  ['change_abs',      'Change $'],
  ['gap_percent',     'Gap %'],
  ['volume',          'Volume'],
  ['rel_volume',      'Daily Rel. Volume'],
  ['newest_headline_at', 'News'],
  ['market_cap',      'Mkt Cap'],
  ['float',           'Float'],
  ['short_interest',  'Short Int.'],
  ['short_ratio',     'Short Ratio'],
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
];

export const STRATEGY_META_MAP: Record<number, StrategyMeta> = Object.fromEntries(
  STRATEGY_META.map(s => [s.id, s]),
);

/** HOD Momo feed columns — Time + shared scanner columns (reusing SCANNER_COLUMNS keys) + Strategy */
export const HOD_MOMO_COLUMNS: [string, string][] = [
  ['time',        'Time'],
  ['symbol',      'Symbol'],
  ['price',       'Price'],
  ['change_pct',  'Change %'],
  ['rvol',        'RVOL'],
  ['float',       'Float'],
  ['gap_pct',     'Gap %'],
  ['volume',      'Volume'],
  ['strategy',    'Strategy'],
];

/** Default master gate config — mirrors backend MasterGateConfig defaults */
export const DEFAULT_MASTER_GATE = {
  hod_required: true,
  surge_pct: 3.0,
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
};
