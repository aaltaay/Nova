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
/** Vite-dev fallback when FastAPI is stale / missing launch-gateway. */
export const NOVA_LAUNCH_GATEWAY_DEV_PATH = '/__nova/launch-gateway';
/** How long the header "Start API" button waits for /api/health after a restart. */
export const NOVA_START_API_HEALTH_TIMEOUT_MS = 45_000;
/** Short probe used to classify Backend unreachable (API_DOWN vs API_WEDGED). */
export const BACKEND_PROBE_TIMEOUT_MS = 2_500;
/** Scanner poll fetch timeout — fail into diagnose instead of hanging for minutes. */
export const SCANNER_FETCH_TIMEOUT_MS = 8_000;
/**
 * REST scanner poll cadence when there is NO IBKR L1 WebSocket driving live
 * price patches (Alpaca discovery) — this poll IS the price feed, so it stays 1Hz.
 */
export const SCANNER_POLL_INTERVAL_MS = 1_000;
/**
 * IBKR membership REST fallback while persistent scanner is still in shadow
 * mode (``IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=false``). When authoritative,
 * ``useScannerData`` stops this interval and relies on ``roster_replace`` /
 * ``table_state`` WebSocket events (ADR 008). Catalysts stay on their own poll.
 * @deprecated Prefer WS roster events once authoritative is flipped.
 */
export const SCANNER_POLL_INTERVAL_IBKR_MS = 5_000;
/** Catalysts / health soft refresh when IBKR structural polls are disabled. */
export const SCANNER_CATALYST_POLL_MS = 60_000;
/**
 * Consecutive scanner-poll failures required before flipping health to
 * disconnected/WEDGED and arming auto-heal. `uvicorn --reload` briefly drops
 * connections while WatchFiles restarts the worker (typically <3s) — without
 * this grace period a single missed poll during a normal dev hot reload
 * looked identical to a real hang and could trigger a competing API restart
 * mid-reload (see PROBLEM_LOG 2026-07-23).
 */
export const SCANNER_HEALTH_FAIL_GRACE_COUNT = 2;

/** Stable outage flags shown in the header + `[Nova][API_FLAG]` console lines. */
export const BACKEND_DIAG_FLAG_DOWN = 'API_DOWN';
export const BACKEND_DIAG_FLAG_WEDGED = 'API_WEDGED';
export const BACKEND_DIAG_FLAG_HTTP = 'API_HTTP';
export const BACKEND_DIAG_FLAG_UNREACHABLE = 'API_UNREACHABLE';

export const BACKEND_DIAG_HINTS: Record<string, string> = {
  [BACKEND_DIAG_FLAG_DOWN]:
    'Nothing answered on the API port — Nova auto-restarts once in dev, or click Start API / Run Nova.bat.',
  [BACKEND_DIAG_FLAG_WEDGED]:
    'Port held by a hung process (health timed out) — Nova auto-restarts once in dev, or click Start API.',
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
  ['volume',              'Volume · RVOL'], // label mirrored in market_ui.SCANNER_VOLUME_COLUMN_LABEL
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
  { id: 1,  name: 'Former Momo Stock',                          color: '#FF9100', audioDefault: false },
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
export const HOD_MOMO_FORMER_MOMO_STRATEGY_ID = 1;
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

/** Visible row window height for the compact HOD scanner. */
export const HOD_MOMO_VISIBLE_ROWS = 30;
/** Row height used to size the viewport — matches `.table-wrapper` Large density.
 * Every row must render at exactly this height (see `.hod-strategy-pills`) so
 * the fixed-window virtualizer's scrollTop -> row-index math stays correct. */
export const HOD_MOMO_ROW_HEIGHT_PX = 32;
/** Sticky header row height included in the scroll viewport. */
export const HOD_MOMO_HEADER_HEIGHT_PX = 30;
/** Extra rows mounted above/below the visible viewport so fast scrolling
 * never shows a blank flash before the next row paints in. Mounted row count
 * stays at HOD_MOMO_VISIBLE_ROWS + 2*this, regardless of total alert count. */
export const HOD_MOMO_OVERSCAN_ROWS = 12;
/** Batch live alert prepends so App does not re-render on every single fire. */
export const HOD_MOMO_ALERT_BATCH_MS = 150;
/** Max strategy pills shown inline per row before collapsing into a "+N" chip
 * (keeps every row a single fixed-height line for virtualization). */
export const HOD_MOMO_MAX_INLINE_STRATEGY_PILLS = 2;

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

// ── Quote Panel (scanner right sidebar) vs Trader window (double-click) ─────
/**
 * Delay before a single click selects the Quote Panel. A second click within
 * this window opens Trader instead (native dblclick is unreliable when the
 * first click re-renders / shifts layout).
 */
export const SYMBOL_DOUBLE_CLICK_MS = 280;
/** Right-hand scanner sidebar that shows quote + fundamentals for the selected symbol. */
export const QUOTE_PANEL_TITLE = 'Quote Panel';
/** Full single-stock page opened by double-click / “Trader” (detached window). */
export const STOCK_VIEW_TITLE = 'Trader';
/** Button / tooltip copy for opening the detached Trader window. */
export const STOCK_VIEW_OPEN_LABEL = 'Trader';
export const STOCK_VIEW_OPEN_TITLE =
  'Open Trader in a new window (same quote data as the Quote Panel, plus charts and trading)';
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
/** Tooltip on the Stock View header symbol chip (double-click to rename). */
export const STOCK_VIEW_SYMBOL_EDIT_TITLE = 'Double-click to change symbol';
/** Aria label for the inline symbol editor after double-click. */
export const STOCK_VIEW_SYMBOL_EDIT_ARIA = 'Change symbol';
/** Max length for ticker typed into the Stock View symbol chip. */
export const STOCK_VIEW_SYMBOL_MAX_LEN = 12;

/** Stock View header — operator mode capsule (Manual / Normal / Fully Automated). */
export const STOCK_VIEW_OPERATOR_MODE_MANUAL = 'Manual';
export const STOCK_VIEW_OPERATOR_MODE_NORMAL = 'Normal';
export const STOCK_VIEW_OPERATOR_MODE_FULL_AUTO = 'Fully Automated';
export const STOCK_VIEW_OPERATOR_MODE_MANUAL_TITLE =
  'Manual mode is not available yet — placeholder only';
export const STOCK_VIEW_OPERATOR_MODE_NORMAL_TITLE =
  'Normal operator mode — place orders manually with existing IBKR safety gates';
export const STOCK_VIEW_OPERATOR_MODE_FULL_AUTO_TITLE =
  'Fully Automated (auto_live) is NO-GO — not selectable';

/** Stock View header — Paper / Live account-mode capsule labels.
 * Clicking these switches which IBKR Gateway port Nova targets and
 * reconnects (persisted to IBKR_GATEWAY_MODE) — see POST /api/ibkr/gateway-mode.
 * Orders stay locked until IBKR_LIVE_TRADING_CONFIRMED is armed separately. */
export const STOCK_VIEW_ACCOUNT_MODE_PAPER = 'Paper';
export const STOCK_VIEW_ACCOUNT_MODE_LIVE = 'Live';
export const STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE =
  'Switch Nova to the paper Gateway port (4002) and reconnect. Requires IB Gateway already logged into a paper account.';
export const STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE =
  'Switch Nova to the live Gateway port (4001) and reconnect. Requires IB Gateway already logged into a live account. Live spend still stays locked until IBKR_LIVE_TRADING_CONFIRMED is set separately.';

// ── Full ticker trading page (double-click / Full view) ───────────────────────
/** Right-rail width (px) on Stock View — charts keep the rest of the viewport. */
export const TICKER_TRADE_SIDE_WIDTH_PX = 360;
/** Drag-to-resize clamp (px) for the Stock View right rail (dense; charts dominate). */
export const TICKER_TRADE_SIDE_WIDTH_MIN_PX = 320;
export const TICKER_TRADE_SIDE_WIDTH_MAX_PX = 440;
/** Desktop breakpoint (px): 2×2 charts + right rail; below stacks rail under charts. */
export const STOCK_VIEW_DESKTOP_MIN_PX = 900;
/**
 * Soft floor (px) for Stock View L2+T&S when space allows.
 * Mirrored as `--sv-depth-min` in stockViewTerminal.css.
 */
export const STOCK_VIEW_DEPTH_MIN_PX = 260;
/** localStorage key: user's saved Stock View quote-panel width (drag-to-resize). */
export const STOCK_VIEW_SIDE_WIDTH_KEY = 'nova.stockView.sideWidthPx';
/**
 * Stock View depth (L2+T&S combined) vs Order Entry vertical split.
 * Drag the horizontal handle between the combined depth module and Open ticket;
 * double-click resets. L2 and T&S stay side-by-side — no splitter between them.
 */
export const STOCK_VIEW_DEPTH_ORDER_SPLIT_KEY = 'nova.stockView.depthOrderSplitPct';
/** Default depth (L2+T&S) share of the trade stack below the quote card (%). */
export const STOCK_VIEW_DEPTH_ORDER_SPLIT_PCT = 72;
/** Clamp so depth stays dominant but the order ticket remains usable. */
export const STOCK_VIEW_DEPTH_ORDER_SPLIT_MIN_PCT = 48;
export const STOCK_VIEW_DEPTH_ORDER_SPLIT_MAX_PCT = 86;
/** Minimum pane height (px) hints for depth / order panes in the trade stack. */
export const STOCK_VIEW_DEPTH_PANE_MIN_PX = 120;
export const STOCK_VIEW_ORDER_PANE_MIN_PX = 140;
/**
 * Chart grid: top row (1m / 5m) vs bottom row (Full Day / 15m).
 * Drag the horizontal handle between rows; double-click resets.
 */
export const STOCK_VIEW_CHART_ROW_SPLIT_KEY = 'nova.stockView.chartRowSplitPct';
export const STOCK_VIEW_CHART_ROW_SPLIT_PCT = 50;
export const STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT = 28;
export const STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT = 72;
/**
 * Charts+rail vs Open Orders dock vertical split (when dock is expanded).
 * Drag the handle above Open Orders; double-click resets.
 */
export const STOCK_VIEW_MAIN_ORDERS_SPLIT_KEY = 'nova.stockView.mainOrdersSplitPct';
export const STOCK_VIEW_MAIN_ORDERS_SPLIT_PCT = 78;
export const STOCK_VIEW_MAIN_ORDERS_SPLIT_MIN_PCT = 52;
export const STOCK_VIEW_MAIN_ORDERS_SPLIT_MAX_PCT = 92;
/** Soft floor (px) for the expanded Open Orders pane. */
export const STOCK_VIEW_OPEN_ORDERS_PANE_MIN_PX = 96;
/** Stock View rail module card titles (uppercase in CSS). */
/** Stock View header market clock tick (ET wall clock + session). */
export const STOCK_VIEW_CLOCK_TICK_MS = 1_000;
export const STOCK_VIEW_CLOCK_TIMEZONE = 'America/New_York';
export const STOCK_VIEW_CLOCK_SESSION_LABELS = {
  premarket: 'Premarket',
  rth: 'RTH',
  afterhours: 'After-hours',
  closed: 'Closed',
} as const;
export const STOCK_VIEW_MODULE_QUOTE_TITLE = 'Stock Quote';
export const STOCK_VIEW_MODULE_L2_TITLE = 'Level 2';
export const STOCK_VIEW_MODULE_TAPE_TITLE = 'Time & Sales';
/** Combined L2 + T&S module title (side-by-side inside one card). */
export const STOCK_VIEW_MODULE_DEPTH_TITLE = 'Level 2 · Time & Sales';
export const STOCK_VIEW_MODULE_OPEN_TITLE = 'Trade';
/** Working / open orders panel (Webull Orders → Working equivalent). */
export const WORKING_ORDERS_PANEL_TITLE = 'Working Orders';
/** Stock View open-orders dock title (bottom strip under charts). */
export const STOCK_VIEW_MODULE_WORKING_ORDERS_TITLE = 'Open Orders';
/**
 * Closed / filled / cancelled session orders (Webull History → Orders Records /
 * filled+cancelled lifecycle from S15). Workspace module id for hide/move.
 */
export const CLOSED_ORDERS_MODULE_ID = 'closed_orders';
export const CLOSED_ORDERS_PANEL_TITLE = 'Closed Orders';
export const CLOSED_ORDERS_EMPTY_MESSAGE =
  'No filled or cancelled orders in this Gateway session.';
export const CLOSED_ORDERS_SAMPLE_BANNER =
  'Sample preview — filled/cancelled rows (not from IBKR)';
/** Closed rows completed within this window get a “just finished” highlight. */
export const CLOSED_ORDERS_RECENT_HIGHLIGHT_MS = 60_000;
/** Re-check recent highlight aging (drop class after the window elapses). */
export const CLOSED_ORDERS_RECENT_TICK_MS = 5_000;
export const CLOSED_ORDERS_RECENT_ROW_TITLE =
  'Completed within the last minute';
/** Positions-row Flatten — full exit via ADR 007 place path (not cancel). */
export const CLOSE_POSITION_BUTTON_LABEL = 'Flatten';
export const CLOSE_POSITION_BUTTON_BUSY_LABEL = 'Flattening…';
export const CLOSE_POSITION_NO_POSITION_TITLE = 'No open position to flatten';
export const CLOSE_POSITION_ACCOUNT_ERROR_TITLE =
  'IBKR account/positions read failed — Flatten disabled until the poll recovers';
export const CLOSE_POSITION_VS_CANCEL_HINT =
  'Flatten closes the entire position with a market order (extended hours when pre/after-market). Cancel only removes a working order. Fill now cancels the rest of one order and markets that remainder.';
/** Working-order panic: cancel rest + market the remaining qty (same side). */
export const FILL_WORKING_ORDER_BUTTON_LABEL = 'Fill now';
export const FILL_WORKING_ORDER_BUTTON_TITLE =
  'Cancel this working order and immediately market the remaining shares (same side). Uses extended hours when the resting order was EH or the session is pre/after-market. Not the same as Flatten (position exit).';
export const FILL_WORKING_ORDER_CONFIRM_PREFIX =
  'Fill now will cancel the resting order and market the remaining shares';
/** localStorage JSON: working/closed/positions column order (drag headers). */
/** Bump when default Open/Closed Orders column order changes (invalidates old layouts). */
export const ORDER_TABLE_COLUMNS_STORAGE_KEY = 'nova.ibkr.orderTable.columns.v5';
export const ORDER_TABLE_COLUMN_DRAG_HINT =
  'Drag to reorder columns · Double-click header to reset';
/** Persisted row-sort stack for working/closed order tables. */
export const ORDER_TABLE_SORT_STORAGE_KEY = 'nova.ibkr.orderTable.sort.v1';
export const ORDER_TABLE_SORT_HINT =
  'Click to sort · Shift+click multi-sort · Drag to reorder columns';
/** Columns that support click-to-sort (row view). */
export const ORDER_TABLE_DATA_SORT_KEYS = [
  'type',
  'session',
  'time',
  'qty',
  'status',
  'filled',
  'remaining',
  'symbol',
  'limit',
  'stop',
  'avg_fill',
  'order_id',
  'filled_at',
] as const;
/** localStorage: `1` = Stock View open-orders dock collapsed. */
export const STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY =
  'nova.stockView.openOrders.collapsed';
/** Default collapsed until the user expands or an order is placed. */
export const STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED = true;
/** localStorage: hide UI-only sample working orders (`1` = hidden). */
export const STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY =
  'nova.stockView.openOrders.sampleHidden';
/** Banner when showing mock rows (never real broker orders). */
export const STOCK_VIEW_OPEN_ORDERS_SAMPLE_BANNER =
  'Sample preview — paper-style rows for this symbol (not from IBKR)';
/**
 * Stock View Orders (Today) — Webull-style session strip (WID-026/027).
 * Segmented: Working | Filled | Canceled | Partial Filled | All.
 */
export const ORDERS_TODAY_TITLE = 'Orders (Today)';
/**
 * Empty-state copy split by *why* the tab is empty, so a real position with
 * no matching orders (symbol/filter mismatch) never looks identical to a
 * Gateway with genuinely zero completed orders for the day — see
 * `backend/ibkr/account.py:refresh_completed_orders_cache`.
 */
export const ORDERS_TODAY_EMPTY_MESSAGE =
  'No completed orders from Gateway yet today.';
export function ordersTodayEmptySymbolMessage(symbol: string): string {
  return `No orders for ${symbol} in this filter today.`;
}
/** Stock View bottom dock: Positions | Orders (Today) | Nova OS. */
export type StockViewDockSurface = 'positions' | 'orders' | 'nova_os';
export const STOCK_VIEW_DOCK_SURFACE_KEY = 'nova.stockView.dock.surface';
export const STOCK_VIEW_DOCK_SURFACE_DEFAULT: StockViewDockSurface = 'orders';
export const STOCK_VIEW_MODULE_POSITIONS_TITLE = 'Positions';
/** Nova OS decide band (gates / news / ticket) — dock tab, not header strip. */
export const STOCK_VIEW_MODULE_NOVA_OS_TITLE = 'Nova OS';
export type OrdersTodayFilterId =
  | 'working'
  | 'filled'
  | 'canceled'
  | 'partial_filled'
  | 'all';
export const ORDERS_TODAY_FILTERS: readonly {
  id: OrdersTodayFilterId;
  label: string;
}[] = [
  { id: 'working', label: 'Working' },
  { id: 'filled', label: 'Filled' },
  { id: 'canceled', label: 'Canceled' },
  { id: 'partial_filled', label: 'Partial Filled' },
  { id: 'all', label: 'All' },
] as const;
export const ORDERS_TODAY_FILTER_STORAGE_KEY =
  'nova.stockView.ordersToday.filter';
export const ORDERS_TODAY_FILTER_DEFAULT: OrdersTodayFilterId = 'all';
/** @deprecated Migrated to ORDERS_TODAY_FILTER_STORAGE_KEY — kept for one-time read. */
export const STOCK_VIEW_ORDERS_TAB_KEY = 'nova.stockView.ordersDock.tab';
export type StockViewOrdersTab = 'open' | 'closed';
export const STOCK_VIEW_ORDERS_TAB_DEFAULT: StockViewOrdersTab = 'open';
/** Suffix pattern for L2: " · TOP {n}". */
export const STOCK_VIEW_MODULE_L2_TOP_PREFIX = 'TOP';
/** Headlines shown in the trading-page side column before "More". */
export const TICKER_TRADE_SIDE_NEWS_COUNT = 3;
/** Default share quantity prefilled in the Open Position ticket (when unlocked). */
export const TICKER_TRADE_DEFAULT_QTY = 100;
/**
 * Temporary single source of truth for manual order size.
 * When non-null, every ticket displays and submits this share qty (ignores presets / % / $).
 * Set to `null` to restore editable sizing.
 */
export const TICKER_TRADE_FORCE_QTY: number | null = 1;
/** Field subtitles on the manual order ticket (Material overline pattern). */
export const TICKER_TRADE_LABEL_SIDE = 'Side';
export const TICKER_TRADE_LABEL_ORDER_TYPE = 'Order Type';
export const TICKER_TRADE_LABEL_QUANTITY = 'Quantity';
export const TICKER_TRADE_LABEL_LIMIT_PRICE = 'Limit Price';
export const TICKER_TRADE_LABEL_STOP_PRICE = 'Stop Price';
export const TICKER_TRADE_LABEL_TRADING_HOURS = 'Trading Hours';
/** Manual order ticket defaults and mode-specific quick-size presets. */
export const TICKER_TRADE_DEFAULT_ORDER_TYPE = 'MKT' as const;
export const TICKER_TRADE_SHARE_PRESETS = [10, 50, 100, 500] as const;
export const TICKER_TRADE_PERCENT_PRESETS = [10, 25, 50, 100] as const;
export const TICKER_TRADE_DOLLAR_PRESETS = [100, 500, 1_000, 5_000] as const;
/**
 * IBKR fractional quantity precision for dollar/percentage sizing and for
 * Positions / Orders / journal qty display (`formatShareQty`).
 * Aligns with Webull’s fractional floor (>0.00001) at practical table precision.
 */
export const TICKER_TRADE_QTY_DECIMALS = 4;
/** Primary CTA before local PIN unlock (does not bypass IBKR spend gates). */
export const TICKER_TRADE_UNLOCK_LABEL = 'Unlock Trading';
/** Primary CTA after PIN unlock — submits the built order (live / offline). */
export const TICKER_TRADE_PLACE_ORDER_LABEL = 'Place an order';
/** Primary CTA after PIN unlock when IBKR Gateway mode is paper. */
export const TICKER_TRADE_PLACE_PAPER_ORDER_LABEL = 'Place Paper order';
/** Hot strip above Stock View / Trading when Gateway mode is paper. */
export const PAPER_TRADING_BANNER_TEXT =
  'PAPER TRADING — orders go to your IBKR paper account, not live money.';
/**
 * Local UI unlock PIN for the Trade ticket (not a server secret).
 * Correct PIN switches the primary button to Place an order for this browser session.
 */
export const TICKER_TRADE_UNLOCK_PIN = '123456';
export const TICKER_TRADE_UNLOCK_PIN_LENGTH = TICKER_TRADE_UNLOCK_PIN.length;
export const TICKER_TRADE_UNLOCK_SESSION_KEY = 'nova.tickerTrade.sessionUnlocked';
/** PIN dialog copy (`TradingPinDialog`). */
export const TICKER_TRADE_UNLOCK_DIALOG_TITLE = 'Trading Verification';
export const TICKER_TRADE_UNLOCK_DIALOG_SUBTITLE = `Please Enter ${TICKER_TRADE_UNLOCK_PIN_LENGTH} Digit Password`;
export const TICKER_TRADE_UNLOCK_DIALOG_CANCEL = 'Cancel';
export const TICKER_TRADE_UNLOCK_FAIL = 'Incorrect unlock code.';
/** localStorage: skip the place-order confirmation dialog. */
export const TICKER_TRADE_SKIP_PLACE_CONFIRM_KEY = 'nova.tickerTrade.skipPlaceConfirm';
export const TICKER_TRADE_PLACE_CONFIRM_TITLE = 'Confirm order';
export const TICKER_TRADE_PLACE_CONFIRM_SKIP_LABEL =
  "Don't show this pop-up again to confirm placing a live order.";
export const TICKER_TRADE_PLACE_CONFIRM_SUBMIT = 'Confirm';
export const TICKER_TRADE_PLACE_CONFIRM_CANCEL = 'Cancel';
/** Plain-language disclosure under the trading action bar. */
export const TICKER_TRADE_ORDER_DISCLOSURE =
  'Orders go through Interactive Brokers only. Alpaca scanning stays read-only.';
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
