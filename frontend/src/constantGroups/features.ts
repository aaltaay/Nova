/** Phase 3 domain group (features.ts). */
import { API_URL } from './chart_api';

// ── Account (header) — former Trading tab + Reports ──────────────────────────
/** Header control next to Today (Live); opens account / habits view. */
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

/** Global shortcuts cheat-sheet (peek on hold / pin on double-tap). */
export const SHORTCUTS_MENU_BINDING: HotkeyBinding = { key: 'm', ctrl: true };
/** Max gap between Ctrl+M presses to count as pin (double-tap). */
export const SHORTCUTS_MENU_DOUBLE_TAP_MS = 450;
export const SHORTCUTS_MENU_TITLE = 'Keyboard shortcuts';
export const SHORTCUTS_MENU_HINT_PEEK =
  'Release to close · press again quickly to pin · Edit or double-click a row to rebind';
export const SHORTCUTS_MENU_HINT_PINNED =
  'Pinned · Esc or menu key to close · Edit or double-click a row to rebind';
export const SHORTCUTS_MENU_REBIND_HINT = 'Press the new shortcut now';
export const SHORTCUTS_MENU_CONFLICT_PREFIX = 'Already used by';

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
  'exit_pos',
  'exit_pos_pct',
  'buy_limit_ask_offset',
  'sell_limit_bid_offset',
] as const;

export type NovaActionKind = (typeof NOVA_ACTION_KINDS)[number];

export const NOVA_ACTION_KIND_LABELS: Record<NovaActionKind, string> = {
  cancel_symbol: 'Cancel open orders (symbol)',
  cancel_and_exit: 'Cancel orders + flatten position',
  exit_pos: 'Exit full position (Flatten)',
  exit_pos_pct: 'Exit position %',
  buy_limit_ask_offset: 'Buy limit at Ask ± offset',
  sell_limit_bid_offset: 'Sell limit at Bid ± offset',
};

/** Default Ask/Bid offset in dollars for limit entries. */
export const NOVA_ACTION_DEFAULT_OFFSET_DOLLARS = 0.05;
/** Default fixed share size for Ask/Bid limit entries. */
export const NOVA_ACTION_DEFAULT_SHARES = 100;
export const NOVA_ACTION_DEFAULT_EXIT_PCTS = [50, 25] as const;

export const NOVA_ACTION_NEEDS_DEPTH: NovaActionKind[] = [
  'buy_limit_ask_offset',
  'sell_limit_bid_offset',
];

export const NOVA_ACTION_DEPTH_DISABLED_REASON =
  'Needs live L2 bid/ask for the open symbol — open Level 2 depth first.';

export const NOVA_ACTION_NO_SYMBOL_MESSAGE = 'Open a symbol first.';
export const NOVA_ACTION_PIN_LOCKED_MESSAGE =
  'Unlock the trading session (PIN) before hotkey orders.';
export const NOVA_ACTION_SPEND_LOCKED_MESSAGE =
  'Orders remain locked by Nova environment safety settings.';
export const NOVA_ACTION_ACCOUNT_ERROR_MESSAGE =
  'IBKR account/positions read failed — Flatten/exit disabled until the poll recovers.';
