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

// ── Backend URL ───────────────────────────────────────────────────────────────
// Set VITE_API_BASE_URL to your Railway public HTTPS domain in production,
// e.g. https://your-service.up.railway.app  (no trailing slash).
// Dev fallback: http://localhost:8000  (matches local uvicorn).
const _rawApiBase: string = (import.meta.env.VITE_API_BASE_URL as string | undefined)
  ?.replace(/\/$/, '') ?? 'http://localhost:8000';
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
