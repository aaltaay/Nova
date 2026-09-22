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

export const GLOBAL_BAR_BRAND = 'Nova';
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

/**
 * Redesigned global bar (approved mockup, 2026-09-22) -- one row on every view:
 * wordmark · session chip · ET clock · connection chip · venue pills · REC
 * chips · [ticker search, centred] · KILL · Day's / Working / TAV / account
 * pill · padlock · gear. The session chip reads the client's Eastern clock
 * (ibkr/extendedSession.ts); the connection chip is the one quiet word about
 * the desk, with the rest of the old status cluster in its tooltip and under
 * the gear.
 */
export const GLOBAL_BAR_SESSION_LABELS = {
  premarket: 'PREMARKET',
  open: 'OPEN',
  afterhours: 'AFTER HOURS',
  closed: 'CLOSED',
} as const;
export const GLOBAL_BAR_SESSION_WORDS = {
  premarket: 'Premarket session',
  open: 'Regular session',
  afterhours: 'After-hours session',
  closed: 'No US equity session on the Eastern clock right now (overnight or weekend)',
} as const;
export const GLOBAL_BAR_SESSION_HOLIDAY_NOTE = 'NYSE holidays are not known to the client.';

/** Connection chip -- one word about the desk, right after the ET clock. */
export const GLOBAL_BAR_CONNECTION_ARIA = 'Connection and data freshness';
export const GLOBAL_BAR_CONNECTION_LIVE_LABEL = 'IBKR live';
export const GLOBAL_BAR_CONNECTION_DELAYED_LABEL = 'IBKR delayed';
export const GLOBAL_BAR_CONNECTION_STALE_LABEL = 'STALE';
export const GLOBAL_BAR_CONNECTION_SAMPLE_LABEL = 'SAMPLE DATA';
export const GLOBAL_BAR_CONNECTION_API_DOWN_LABEL = 'API down';
export const GLOBAL_BAR_CONNECTION_SAMPLE_TITLE =
  'Nova Marketing Sample Data -- isolated fixtures, never live market data. Exit the sample desk to see the live Gateway.';
export const GLOBAL_BAR_CONNECTION_API_UP_TITLE = 'Nova API process is reachable on port 8000.';
export const GLOBAL_BAR_CONNECTION_API_DOWN_TITLE =
  'Nova API is unreachable -- start the backend (port 8000).';
export const GLOBAL_BAR_CONNECTION_CLICK_HINT =
  'Click for the API and Gateway checklist. Double-click launches the current Gateway target.';
export const GLOBAL_BAR_CONNECTION_PRICES_PREFIX = 'Prices:';
export const GLOBAL_BAR_CONNECTION_SCANNER_MODE_PREFIX = 'Scanner mode:';
export const GLOBAL_BAR_FEED_FALLBACK_TITLE =
  'SIP feed was rejected; automatically fell back to IEX. Change in Settings if your plan supports SIP.';
export const globalBarLegacyFeedTitle = (feedLabel: string): string =>
  `Legacy Alpaca data feed: ${feedLabel} (not a product scanner source)`;

/** Centre of the bar: the ticker search. Enter opens the symbol in the Trader. */
export const GLOBAL_BAR_SEARCH_PLACEHOLDER = 'Symbol';
export const GLOBAL_BAR_SEARCH_ARIA = 'Look up symbol';
export const GLOBAL_BAR_SEARCH_TITLE = 'Type a symbol and press Enter to open it in the Trader';

/** Gear menu -- the homes for what left the bar. */
export const GLOBAL_BAR_GEAR_ARIA = 'Nova menu';
export const GLOBAL_BAR_GEAR_TITLE = 'Reload backend · Theme · Gateway & feed status · Settings';
export const GLOBAL_BAR_MENU_THEME_LABEL = 'Theme';
export const GLOBAL_BAR_MENU_GATEWAY_LABEL = 'Gateway & feed status';
export const GLOBAL_BAR_MENU_GATEWAY_TITLE = 'Open the API and Gateway checklist';
export const GLOBAL_BAR_MENU_SAMPLE_OPEN_LABEL = 'Open sample data';
export const GLOBAL_BAR_MENU_SAMPLE_EXIT_LABEL = 'Exit sample data';
export const GLOBAL_BAR_MENU_SAMPLE_TITLE =
  'Isolated Nova Marketing Sample Data fixtures -- never mixed with live market data';
export const GLOBAL_BAR_MENU_SETTINGS_LABEL = 'Settings…';
