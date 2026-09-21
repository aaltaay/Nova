/**
 * Shared GlobalAppBar labels and layout tunables.
 * Mounted once in AppShell so every live page inherits the same chrome.
 * Primary row is desk chrome; bot controls live on a second row (#230).
 */

/** Fixed height of the Webull-style top status row (px). Bot row is extra. */
export const GLOBAL_APP_BAR_HEIGHT_PX = 40;

/** Accessible name for the bot-only second header row. */
export const GLOBAL_BAR_BOT_ROW_LABEL = 'Bot Autonomy';

/** Account cluster (Day P&L / Net Liq / BP / position marks) while Gateway is up. */
export const IBKR_ACCOUNT_POLL_MS = 1_000;
/** Working + closed orders -- slower so the 1s cluster poll does not hammer IBKR. */
export const IBKR_ORDERS_POLL_MS = 5_000;
/** One shared /api/ibkr/status interval for every useIbkrStatus subscriber. */
export const IBKR_STATUS_POLL_MS = 5_000;
/** Consecutive failed polls before last-good `connected` is forced false. */
export const IBKR_STATUS_STALE_AFTER_MISSES = 2;
/** sessionStorage last successful /api/ibkr/status -- avoids a false Disconnected flash. */
export const IBKR_STATUS_SESSION_KEY = 'nova.ibkr.status.last';

/**
 * Cross-window leader heartbeat stale -- another Electron/Vite window may take
 * the account/bot HTTP poll. Stay under 2s so Day P&L does not feel like 5s.
 */
export const DESK_POLL_LEADER_STALE_MS = 1_800;
/** Followers treat a snapshot older than this as missing and try to claim. */
export const DESK_POLL_SNAPSHOT_MAX_AGE_MS = 2_000;
export const DESK_POLL_ACCOUNT_SHARE = 'ibkr-account';
export const DESK_POLL_BOT_SHARE = 'bot-session';
/** Bot header + Strategy share one poller; this is the armed interval. */
export const DESK_BOT_POLL_MS = 2_500;
export const DESK_POLL_LEADER_KEY_PREFIX = 'nova.desk.poll.leader.';
export const DESK_POLL_SNAP_KEY_PREFIX = 'nova.desk.poll.snap.';
export const DESK_POLL_CHANNEL_PREFIX = 'nova-desk-poll-';
export const DESK_POLL_TAB_SESSION_KEY = 'nova.desk.poll.tab';

export const GLOBAL_BAR_BRAND = 'NOVA';
export const GLOBAL_BAR_NAV_SCANNER = 'Scanner';
export const GLOBAL_BAR_NAV_TRADER = 'Trader';
export const GLOBAL_BAR_NAV_SCANNER_TITLE =
  'Return to the scanner dashboard without closing Trader tape or Level 2';
export const GLOBAL_BAR_NAV_TRADER_TITLE =
  'Open Trader View for the selected symbol, or SPY if none is selected. Use the arrow for QQQ / IWM.';
export const GLOBAL_BAR_NAV_TRADER_DISABLED_TITLE =
  'Select a symbol first, then open Trader View';

/**
 * Compact account cluster, Webull order: Day's | Working | TAV | account pill.
 * One row on every venue; the cards under Day's / TAV hold the rest.
 */
export const GLOBAL_BAR_DAY_PNL_LABEL = "Day's";
export const GLOBAL_BAR_DAY_PNL_TITLE =
  "Day's P&L -- realized plus unrealized since the day started. The percent is against the account value at the start of the day.";
export const GLOBAL_BAR_TAV_LABEL = 'TAV';
export const GLOBAL_BAR_TAV_TITLE = 'Total Account Value -- IBKR NetLiquidation';
export const GLOBAL_BAR_WORKING_LABEL = 'Working';

/** Only when Gateway / market-data session is down. */
export const GLOBAL_BAR_OFFLINE_CHIP = 'IBKR offline';
/** Gateway up; /api/ibkr/account not ready yet — never use OFFLINE_CHIP here. */
export const GLOBAL_BAR_ACCOUNT_LOADING_CHIP = 'Account…';
/** Gateway up; account poll failed — distinct from session offline. */
export const GLOBAL_BAR_ACCOUNT_UNAVAILABLE_CHIP = 'Account unavailable';
export const GLOBAL_BAR_ACCOUNT_UNAVAILABLE_TITLE = 'Account snapshot unavailable';
export const GLOBAL_BAR_ACCOUNT_LOADING_TITLE = 'Gateway connected -- loading account snapshot';
export const GLOBAL_BAR_OFFLINE_PLACEHOLDER = '--';

/** Card under Day's. */
export const GLOBAL_BAR_DAY_CARD_ARIA = "Day's P&L details";
export const GLOBAL_BAR_CARD_OPEN_PNL = 'Open P&L';
export const GLOBAL_BAR_CARD_DAY_PNL = "Day's P&L";
export const GLOBAL_BAR_CARD_REALIZED_PNL = "Day's Realized P&L";
/** Card under TAV. Excess Liquidity is IBKR-only and omitted when IBKR does not report it. */
export const GLOBAL_BAR_TAV_CARD_ARIA = 'Account value details';
export const GLOBAL_BAR_CARD_TAV = 'Total Account Value';
export const GLOBAL_BAR_CARD_CASH = 'Cash';
export const GLOBAL_BAR_CARD_BP = 'Buying Power';
export const GLOBAL_BAR_CARD_EXCESS_LIQUIDITY = 'Excess Liquidity';
export const GLOBAL_BAR_CARD_GPV = 'Gross Position Value';

export const GLOBAL_BAR_WORKING_MENU_TITLE = 'Working orders';
export const GLOBAL_BAR_WORKING_ORDERS_LABEL = 'Working Orders';
export const GLOBAL_BAR_FILLED_TODAY_LABEL = 'Filled Today';
export const GLOBAL_BAR_CANCELED_FAILED_LABEL = 'Canceled & Failed';
export const GLOBAL_BAR_CANCEL_ALL_STOCKS = 'Cancel All (Stocks)';
export const GLOBAL_BAR_CANCEL_ALL_OPTIONS = 'Cancel All Single Options';
export const GLOBAL_BAR_CANCEL_ALL_OPTIONS_TITLE =
  'Options trading is not available in Nova yet';
export const GLOBAL_BAR_VIEW_ALL_ORDERS = 'View All Orders';
export const GLOBAL_BAR_CANCEL_ALL_CONFIRM_TITLE = 'Cancel all working stock orders?';
export const GLOBAL_BAR_CANCEL_ALL_CONFIRM_BODY =
  'This cancels every open stock order across all symbols. This cannot be undone.';
export const GLOBAL_BAR_CANCEL_ALL_CONFIRM_LABEL = 'Cancel all';
export const GLOBAL_BAR_CANCEL_ALL_EMPTY_TITLE = 'No working stock orders to cancel';

/** CustomEvent name — DashboardPage opens the Account/Trading tab. */
export const GLOBAL_BAR_OPEN_TRADING_TAB_EVENT = 'nova:open-trading-tab';

export const GLOBAL_BAR_MODE_PAPER = 'Paper';
export const GLOBAL_BAR_MODE_LIVE = 'Live';
export const GLOBAL_BAR_MODE_SIM = 'Sim';
export const GLOBAL_BAR_MODE_CAPTURE = 'Capture';
export const GLOBAL_BAR_MODE_DISCONNECTED = 'Disconnected';

/** Account + Settings on the shared GlobalAppBar (Scanner + Trader). */
export const GLOBAL_BAR_ACCOUNT_LABEL = 'Account';
export const GLOBAL_BAR_ACCOUNT_TITLE =
  'Account overview — positions, orders, and trading habit reports';
/** Hover/focus popover under the Account icon (holds Fund account). */
export const GLOBAL_BAR_ACCOUNT_MENU_LABEL = 'Account shortcuts';
/** Opens IBKR Client Portal only -- Nova never deposits. */
export const GLOBAL_BAR_FUND_ACCOUNT_LABEL = 'Fund account';
export const GLOBAL_BAR_FUND_ACCOUNT_TITLE =
  'Opens IBKR Client Portal -- then Transfer & Pay -> Deposit Funds. Nova does not deposit.';
/**
 * Account pill -- structure + class + the full account id, e.g.
 * "Individual Margin (U1234567)" (issue #181 chip folded in). Structure is
 * IBKR's raw AccountType (ownership); class is the backend-stamped
 * account_class. A word that is not reported is omitted, never guessed. The
 * full id is what tells two accounts apart; the login username is never
 * exposed by the API, so the id is the identity Nova can state truthfully.
 */
export const GLOBAL_BAR_ACCOUNT_TYPE_CASH = 'Cash';
export const GLOBAL_BAR_ACCOUNT_TYPE_MARGIN = 'Margin';
/** Raw IBKR AccountType -> the word on the pill. Anything else is omitted. */
export const GLOBAL_BAR_ACCOUNT_STRUCTURE_LABELS: Readonly<Record<string, string>> = {
  INDIVIDUAL: 'Individual',
  JOINT: 'Joint',
  IRA: 'IRA',
  TRUST: 'Trust',
  LLC: 'LLC',
  CORPORATION: 'Corporation',
  PARTNERSHIP: 'Partnership',
};
export const GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP =
  'Stock shorting requires a margin account. Nova IBKR_SHORT_ENABLED is a separate env gate.';
export const GLOBAL_BAR_ACCOUNT_TYPE_RAW_PREFIX = 'IBKR AccountType:';
export const GLOBAL_BAR_ACCOUNT_TYPE_RAW_MISSING = '(missing)';
export const GLOBAL_BAR_ACCOUNT_TYPE_TRADING_PREFIX = 'IBKR TradingType-S:';
export const GLOBAL_BAR_ACCOUNT_PILL_ARIA = 'Trading account';
/** Menu under the pill: every managed account on the login, the active one marked. */
export const GLOBAL_BAR_ACCOUNT_PILL_MENU_LABEL = 'Managed accounts';
export const GLOBAL_BAR_ACCOUNT_PILL_ACTIVE_MARK = 'active';
export const GLOBAL_BAR_ACCOUNT_PILL_SWITCH_NOTE =
  'Nova trades the account the Gateway is logged into. Switching accounts happens in IB Gateway / TWS, not here.';
export const globalBarAccountIdTooltip = (id: string, kind: string, others: string[]): string => {
  const what = kind === 'paper' ? 'paper' : kind === 'live' ? 'LIVE' : 'unclassified';
  const rest = others.length ? ` Other managed accounts on this login: ${others.join(', ')}.` : '';
  return `IBKR account ${id} (${what}). This is what Nova is logged into; the login username is never exposed by the API.${rest}`;
};
export const GLOBAL_BAR_SETTINGS_LABEL = 'Settings';
export const GLOBAL_BAR_SETTINGS_TITLE = 'Open Settings';

/** Header Emergency KILL -- compose existing cancel / flatten / L0 / desk lock. */
export const GLOBAL_BAR_EMERGENCY_KILL_LABEL = 'Emergency KILL';
export const GLOBAL_BAR_EMERGENCY_KILL_OPS = [
  'Cancel all working orders',
  'Flatten all open positions (market)',
  'Set Bot Autonomy to L0',
  'Lock trading until you unlock',
] as const;
export const GLOBAL_BAR_EMERGENCY_KILL_TITLE =
  GLOBAL_BAR_EMERGENCY_KILL_OPS.join('\n');
export const GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_TITLE = 'Emergency KILL?';
export const GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_BODY = [
  'This uses the existing cancel-all, account flatten, Bot Autonomy PATCH, and header trade-lock doors.',
  'L0 and the header lock apply first so the bot cannot re-enter while cancel/flatten run, then again after.',
  '',
  ...GLOBAL_BAR_EMERGENCY_KILL_OPS.map((op) => `- ${op}`),
  '',
  'Unlock afterwards with the header lock (PIN). Place stays blocked until you unlock.',
].join('\n');
export const GLOBAL_BAR_EMERGENCY_KILL_FAIL_TITLE =
  'Emergency KILL did not finish cleanly';
export const GLOBAL_BAR_EMERGENCY_KILL_BUSY_LABEL = 'KILL running…';
