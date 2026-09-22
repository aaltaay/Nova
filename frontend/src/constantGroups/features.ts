/** Phase 3 domain group (features.ts). */
import { API_URL } from './chart_api';

// ── Account — former Trading tab + Reports (GlobalAppBar + sample AppHeader) ─
/** Account control label (GlobalAppBar; sample AppHeader). */
export const ACCOUNT_NAV_LABEL = 'Account';
export const ACCOUNT_NAV_TITLE =
  'Account overview — positions, orders, and trading habit reports';
/** Account page sections (Overview = IBKR positions/orders; Reports = P&L habits). */
export const ACCOUNT_SECTION_OVERVIEW = 'Overview';
export const ACCOUNT_SECTION_REPORTS = 'Reports';
export type AccountSectionId = 'overview' | 'reports';
export const ACCOUNT_SECTION_DEFAULT: AccountSectionId = 'overview';

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
/** Fixed T&S row height so the DOM window can scroll the full ring. */
export const TAPE_ROW_HEIGHT_PX = 22;
/** Extra T&S rows mounted above/below the viewport. */
export const TAPE_OVERSCAN_ROWS = 8;
/** Used before ResizeObserver reports a real pane height. */
export const TAPE_VIEWPORT_FALLBACK_ROWS = 20;
/** scrollTop at or below this stays pinned to the newest prints. */
export const TAPE_STICK_TOP_PX = 4;
export const TAPE_SECTION_TITLE = 'Time & Sales';
/** Header badge while the live tape feed is subscribed. */
export const TAPE_STATUS_LIVE = 'LIVE';
export const TAPE_EMPTY_LABEL = 'Waiting for prints…';
/** Row tooltip for prints IBKR flags unreported (odd lot / Form T). */
export const TAPE_UNREPORTED_TITLE =
  'Unreported print (odd lot / Form T) -- excluded from candles, last and volume';
export const TAPE_COL_HEADERS = {
  time: 'Time',
  price: 'Price',
  size: 'Size',
  exchange: 'Exch',
} as const;
/** localStorage: T&S min print size. 0 / empty = show all (display filter only). */
export const TAPE_MIN_SIZE_STORAGE_KEY = 'nova.tape.minSize';
export const TAPE_MIN_SIZE_FILTER_TITLE = 'Min size';
export const TAPE_MIN_SIZE_FILTER_HINT = 'Empty or 0 shows all prints';
export const TAPE_MIN_SIZE_FILTER_MENU_WIDTH_PX = 220;
export const TAPE_MIN_SIZE_FILTER_MENU_HEIGHT_PX = 104;
export const TAPE_MIN_SIZE_FILTER_MENU_PAD_PX = 8;
/** Aggressor labels (legacy / tests). Tape UI encodes side via row tint only. */
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

/** Scanner Earnings column: three dots for tomorrow / today / yesterday. */
export const EARNINGS_DOT_SESSION_BMO = 'before open';
export const EARNINGS_DOT_SESSION_AMC = 'after close';
export const EARNINGS_DOT_SESSION_INTRADAY = 'intraday';
export const EARNINGS_DOT_ESTIMATED = 'estimated';
export const EARNINGS_DOT_EMPTY_TITLE = 'No earnings date';

/** Earnings tab (calendar metadata, not an IBKR scanner lease -- see
 * single-market-data-feed.mdc). Range chips + lane truncation + poll cadence. */
export const EARNINGS_RANGES = ['today', 'tomorrow', 'week', 'month'] as const;
export const EARNINGS_RANGE_LABELS: Record<string, string> = {
  today: 'Today',
  tomorrow: 'Tomorrow',
  week: 'This week',
  month: 'This month',
};
export const EARNINGS_LANE_PREVIEW_CAP = 8;
export const EARNINGS_POLL_MS = 60_000;
export const EARNINGS_SESSION_LABELS: Record<string, string> = {
  bmo: 'Before open',
  amc: 'After close',
  intraday: 'Intraday',
};
export const EARNINGS_NO_KEY_MESSAGE =
  'Finnhub is not configured -- set FINNHUB_API_KEY in .env to load the earnings calendar.';
export const EARNINGS_MISSING_KEY_STALE_MESSAGE =
  'Finnhub is not configured -- showing the last cached earnings calendar.';
export const EARNINGS_RATE_LIMITED_MESSAGE =
  'Finnhub rate-limited the earnings calendar. Retry shortly.';
export const EARNINGS_RATE_LIMITED_STALE_MESSAGE =
  'Finnhub rate-limited -- showing the last cached earnings calendar.';

/** HOD Strategies filter dropdown — tall enough to show most strategies without scroll. */
export const HOD_STRATEGY_FILTER_MAX_HEIGHT_PX = 520;

// ── Outbound alerts (Phase D — mirrors backend/constants.py ALERTS_*) ────────
export const ALERTS_CHANNEL_TYPES = ['discord', 'telegram', 'webhook'] as const;
export type AlertChannelType = (typeof ALERTS_CHANNEL_TYPES)[number];
export const ALERTS_CHANNEL_TYPE_LABELS: Record<AlertChannelType, string> = {
  discord: 'Discord webhook',
  telegram: 'Telegram bot',
  webhook: 'Generic webhook',
};
export const ALERTS_API = `${API_URL}/alerts`;

// ── Executor hotkeys (Phase G) ───────────────────────────────────────────────
/** Automation panel keyboard shortcuts — display + default bindings only. */
export const HOTKEY_ACTIONS = [
  'approve_staged',
  'reject_staged',
  'arm_confirm',
  'disarm_signal',
  'focus_flatten',
  'kill_switch',
] as const;

export type HotkeyAction = (typeof HOTKEY_ACTIONS)[number];

export interface HotkeyBinding {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean;
}

/** Default executor hotkeys (Automation panel active). */
export const HOTKEY_DEFAULTS: Record<HotkeyAction, HotkeyBinding> = {
  approve_staged: { key: 'a', shift: true },
  reject_staged: { key: 'r', shift: true },
  arm_confirm: { key: 'c', shift: true, ctrl: true },
  disarm_signal: { key: 's', shift: true, ctrl: true },
  focus_flatten: { key: 'f', shift: true, ctrl: true },
  kill_switch: { key: 'k', shift: true, ctrl: true },
};

export const HOTKEY_ACTION_LABELS: Record<HotkeyAction, string> = {
  approve_staged: 'Approve first staged bracket',
  reject_staged: 'Reject first staged ticket',
  arm_confirm: 'Raise to Confirm',
  disarm_signal: 'Drop to Signal',
  focus_flatten: 'Open Flatten dialog (typed confirm still required)',
  kill_switch: 'Stop Automation',
};

/** Order-placement hotkeys blocked while control mode is signal. */
export const HOTKEY_ORDER_ACTIONS: HotkeyAction[] = [
  'approve_staged',
  'reject_staged',
  'arm_confirm',
];

export const HOTKEY_SIGNAL_BLOCKED_MESSAGE =
  'Order hotkeys disabled in Signal mode — raise to Confirm first.';

/**
 * Global shortcuts cheat-sheet.
 * Default is Ctrl+Alt (hold = peek, release = close; double-tap to pin).
 */
export const SHORTCUTS_MENU_BINDING: HotkeyBinding = { key: 'Alt', ctrl: true };
/**
 * Bump when the product default menu chord changes — loadProfile clears any
 * stored shortcutsMenuKey once so Listening experiments cannot leave the menu dead.
 */
export const SHORTCUTS_MENU_DEFAULT_EPOCH = 'ctrl-alt-2026-07-29';
export const SHORTCUTS_MENU_EPOCH_STORAGE_KEY = 'nova.hotkeys.menu-default-epoch';
/** Max gap between menu-key presses to count as pin (double-tap). */
export const SHORTCUTS_MENU_DOUBLE_TAP_MS = 450;
export const SHORTCUTS_MENU_TITLE = 'Keyboard shortcuts';
export const SHORTCUTS_MENU_HINT_PEEK =
  'Hold Ctrl+Alt · release to close · tap twice to pin · Key rebinds · Edit changes the action';
export const SHORTCUTS_MENU_HINT_PINNED =
  'Pinned · Esc or Ctrl+Alt closes · Key rebinds · Edit changes the action · trash needs a second click';
export const SHORTCUTS_MENU_REBIND_HINT = 'Press the new shortcut now';
export const SHORTCUTS_MENU_CONFLICT_PREFIX = 'Already used by';
export const SHORTCUTS_MENU_KEY_BTN = 'Key';
export const SHORTCUTS_MENU_ACTION_BTN = 'Edit';
export const SHORTCUTS_MENU_DELETE_CONFIRM = 'Delete?';
/** First trash click only arms; second click within this window deletes. */
export const SHORTCUTS_MENU_DELETE_ARM_MS = 4000;

// ── DAS-compatible hotkey manager (Phase G2 / G3) ────────────────────────────
/** Shown in Settings → Hotkeys for the DAS import table. */
export const HOTKEY_MANAGER_INACTIVE_BANNER =
  'Imported DAS commands stay inactive until you Map to Nova Action. Raw scripts never auto-run.';

/** DAS short-script byte threshold before ~length chunked encoding. */
export const HOTKEY_HTK_SHORT_SCRIPT_MAX_BYTES = 51;
export const HOTKEY_HTK_CHUNK_BYTES = 51;
export const HOTKEY_HTK_NAME_MAX_CHARS = 99;

// ── Nova Actions (Phase G3 — typed, executable) ──────────────────────────────
export const NOVA_ACTION_KINDS = [
  'cancel_symbol',
  'cancel_and_exit',
  'cancel_all_orders',
  'exit_pos',
  'exit_pos_pct',
  'buy_market',
  'buy_limit_ask_offset',
  'sell_limit_bid_offset',
  'sell_limit_ask_offset',
  'sell_pos_pct_ask',
  'sell_pos_pct_bid_offset',
] as const;

export type NovaActionKind = (typeof NOVA_ACTION_KINDS)[number];

export const NOVA_ACTION_KIND_LABELS: Record<NovaActionKind, string> = {
  cancel_symbol: 'Cancel open orders (symbol)',
  cancel_and_exit: 'Cancel orders + flatten position',
  cancel_all_orders: 'Cancel all working orders (account)',
  exit_pos: 'Exit full position (Flatten)',
  exit_pos_pct: 'Exit position % (market)',
  buy_market: 'Buy market (fixed shares)',
  buy_limit_ask_offset: 'Buy limit at Ask ± offset',
  sell_limit_bid_offset: 'Sell limit at Bid ± offset',
  sell_limit_ask_offset: 'Sell limit at Ask ± offset',
  sell_pos_pct_ask: 'Sell long % at Ask (limit)',
  sell_pos_pct_bid_offset: 'Sell long % at Bid − offset (limit)',
};

/** Default Ask/Bid offset in dollars for limit entries. */
export const NOVA_ACTION_DEFAULT_OFFSET_DOLLARS = 0.05;
/** Webull-style Bid− exit offset ($0.03). */
export const NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS = 0.03;
/** Default fixed share size for Ask/Bid limit entries. */
export const NOVA_ACTION_DEFAULT_SHARES = 100;
/** Default shares for buy_market (quick paper/live smoke). */
export const NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES = 1;
/** Desk F1/F2/F5 Ask+/Bid- size -- 1 share either way. */
export const NOVA_ACTION_DESK_SHARES = 1;
/**
 * Bump when F1/F2/F5 desk defaults change -- loadProfile rewrites those rows
 * once so an older local profile does not keep Ctrl+Shift+B / 100 shares.
 */
export const DESK_ASK_BID_HOTKEY_EPOCH = 'f1-f5-eh-2026-08-17';
export const DESK_ASK_BID_HOTKEY_EPOCH_KEY = 'nova.hotkeys.desk-ask-bid-epoch';
export const NOVA_ACTION_DEFAULT_EXIT_PCTS = [50, 25] as const;

export const NOVA_ACTION_NEEDS_DEPTH: NovaActionKind[] = [
  'buy_limit_ask_offset',
  'sell_limit_bid_offset',
  'sell_limit_ask_offset',
  'sell_pos_pct_ask',
  'sell_pos_pct_bid_offset',
];

export const NOVA_ACTION_DEPTH_DISABLED_REASON =
  'Needs live L2 bid/ask for the open symbol — open Level 2 depth first.';

export const NOVA_ACTION_NO_SYMBOL_MESSAGE = 'Open a symbol first.';
export const NOVA_ACTION_PIN_LOCKED_MESSAGE =
  'Unlock the trading session (PIN) before hotkey orders.';
export const NOVA_ACTION_SPEND_LOCKED_MESSAGE =
  'Orders remain locked by Nova environment safety settings.';
export const EXECUTION_TRANSPORT_TIMEOUT_MESSAGE =
  'Order request timed out -- IB loop is busy (charts/historicals). Check Working Orders before retrying.';
export const EXECUTION_TRANSPORT_UNREACHABLE_MESSAGE =
  'Could not reach Nova API. Check Working Orders / IB Gateway before retrying. Do not assume the order was sent.';
export const EXECUTION_TRANSPORT_FAILED_MESSAGE =
  'Order request failed. Check Working Orders before retrying.';
export const NOVA_ACTION_ACCOUNT_ERROR_MESSAGE =
  'IBKR account/positions read failed -- Flatten/exit disabled until the poll recovers.';
export const NOVA_ACTION_IN_FLIGHT_MESSAGE =
  'That action is still running -- wait for the order receipt before firing again.';

// ── Settings > Hot Keys: the two-pane editor inline in the section ───────────
export const HOTKEYS_SECTION_TITLE = 'Hot Keys';
export const HOTKEYS_SECTION_SUBTITLE =
  'Hotkey settings for single and group orders. Edits save as you make them.';
export const HOTKEYS_SETTINGS_LIST_TITLE = 'Trading Hotkeys';
export const HOTKEYS_EDITOR_GROUP_STOCKS = 'Stocks';
export const HOTKEYS_EDITOR_EMPTY = 'Select a hotkey or press + to create one.';
export const HOTKEYS_ROW_DISABLED_TITLE = 'Disabled -- turn it on in the editor';
export const HOTKEYS_DELETE_HINT = 'Delete needs a second click';
export const HOTKEYS_SETTINGS_DONE = 'Done';
export const HOTKEYS_SETTINGS_RESET = 'Reset to Default';
export const HOTKEYS_CREATE_ADD_LABEL = 'Create customized button';
export const HOTKEYS_CREATE_DIALOG_TITLE = 'Create a Customized Button';
export const HOTKEYS_CREATE_NAME_LABEL = 'Button Name';
export const HOTKEYS_CREATE_APPLY_LABEL = 'Button Apply To';
export const HOTKEYS_CREATE_APPLY_STOCK = 'Stock';
export const HOTKEYS_CREATE_SIDE_LABEL = 'Side';
export const HOTKEYS_CREATE_SIDE_BUY = 'Buy';
export const HOTKEYS_CREATE_SIDE_SELL = 'Sell';
export const HOTKEYS_CREATE_ACTION_LABEL = 'Action';
export const HOTKEYS_CREATE_CANCEL = 'Cancel';
export const HOTKEYS_CREATE_SUBMIT = 'Create';
export const HOTKEYS_ADVANCED_DAS_TITLE = 'Advanced: DAS import';
export const HOTKEYS_ADVANCED_DAS_HINT =
  'Import .htk files and Map rows to typed Nova Actions. Raw DAS scripts never auto-run.';
export const HOTKEYS_EMPTY_LIST = 'No Nova Actions yet -- press + to add one.';
export const HOTKEYS_DEFAULT_CUSTOM_NAME = 'Custom1';

/** Suspense copy while a lazy Settings / Account / Backtest chunk loads (D-031). */
export const TAB_CHUNK_LOADING = 'Loading…';

