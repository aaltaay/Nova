/** Phase 3 domain group (chart_api.ts). */

import type { ChartIndicatorId, ChartOverlayId, ChartOscillatorId } from './market_ui';

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
/** Vite-dev-only path that kills port 8000 and starts `scripts/Start-NovaApi.ps1`. */
export const NOVA_START_API_DEV_PATH = '/__nova/start-api';
/** How long the header "Start API" button waits for /api/health after a restart. */
export const NOVA_START_API_HEALTH_TIMEOUT_MS = 45_000;
/** Short probe used to classify Backend unreachable (API_DOWN vs API_WEDGED). */
export const BACKEND_PROBE_TIMEOUT_MS = 2_500;
/** Scanner poll fetch timeout — fail into diagnose instead of hanging for minutes. */
export const SCANNER_FETCH_TIMEOUT_MS = 8_000;

/** Stable outage flags shown in the header + `[Nova][API_FLAG]` console lines. */
export const BACKEND_DIAG_FLAG_DOWN = 'API_DOWN';
export const BACKEND_DIAG_FLAG_WEDGED = 'API_WEDGED';
export const BACKEND_DIAG_FLAG_HTTP = 'API_HTTP';
export const BACKEND_DIAG_FLAG_UNREACHABLE = 'API_UNREACHABLE';

export const BACKEND_DIAG_HINTS: Record<string, string> = {
  [BACKEND_DIAG_FLAG_DOWN]:
    'Nothing answered on the API port — click Start API or run Run Nova.bat.',
  [BACKEND_DIAG_FLAG_WEDGED]:
    'Port is held by a hung process (health timed out) — click Start API to kill+restart.',
  [BACKEND_DIAG_FLAG_HTTP]:
    'API process responded but /api/health was not OK — check backend\\logs\\api-console.log.',
  [BACKEND_DIAG_FLAG_UNREACHABLE]:
    'Backend unreachable — click Start API, or double-click Run Nova.bat.',
};

declare global {
  interface Window {
    __NOVA_API_BASE__?: string;
    novaDesktop?: {
      isDesktop: boolean;
      apiBase: string;
      getVersion: () => Promise<string>;
      /** Electron IPC: open Stock View in a child BrowserWindow. */
      openStockView?: (url: string) => Promise<boolean>;
      /** Electron IPC: stop + start the local FastAPI sidecar, then wait for health. */
      restartApi?: () => Promise<{ ok: boolean; error?: string }>;
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
/** Scanner L1 reconcile / UI age clock (mirrors backend IBKR_L1_RECONCILE_SEC). */
export const IBKR_TABLE_REPRICE_INTERVAL_SEC = 1.0;
/** Mark header stale if no successful price_patch within this many seconds. */
export const SCANNER_PRICE_STALE_SEC = 5.0;
/** Per-row stale tint when last IB L1 quote is older than this (mirrors backend). */
export const IBKR_L1_ROW_STALE_SEC = 3.0;
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
/** Full single-stock page opened by double-click / “Stock View” (detached window). */
export const STOCK_VIEW_TITLE = 'Stock View';
/** Button / tooltip copy for opening the detached Stock View window. */
export const STOCK_VIEW_OPEN_LABEL = 'Stock View';
export const STOCK_VIEW_OPEN_TITLE =
  'Open Stock View in a new window (same quote data as the Quote Panel, plus charts and trading)';
/**
 * window.open feature string — size/popup flags force a real OS window.
 * Bare `_blank` with no features opens a browser tab (Chrome/Edge).
 * Do NOT add noopener here: it makes window.open return null.
 */
export const STOCK_VIEW_WINDOW_WIDTH = 1440;
export const STOCK_VIEW_WINDOW_HEIGHT = 900;
export const STOCK_VIEW_WINDOW_LEFT = 72;
export const STOCK_VIEW_WINDOW_TOP = 48;
export const STOCK_VIEW_WINDOW_FEATURES = [
  'popup=yes',
  `width=${STOCK_VIEW_WINDOW_WIDTH}`,
  `height=${STOCK_VIEW_WINDOW_HEIGHT}`,
  `left=${STOCK_VIEW_WINDOW_LEFT}`,
  `top=${STOCK_VIEW_WINDOW_TOP}`,
  'menubar=no',
  'toolbar=no',
  'location=yes',
  'status=no',
  'resizable=yes',
  'scrollbars=yes',
].join(',');
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
