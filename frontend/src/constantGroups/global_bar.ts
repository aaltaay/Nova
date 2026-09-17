/**
 * Shared GlobalAppBar labels and layout tunables.
 * Mounted once in AppShell so every live page inherits the same chrome.
 * Primary row is desk chrome; bot controls live on a second row (#230).
 */

/** Fixed height of the Webull-style top status row (px). Bot row is extra. */
export const GLOBAL_APP_BAR_HEIGHT_PX = 40;

/** Accessible name for the bot-only second header row. */
export const GLOBAL_BAR_BOT_ROW_LABEL = 'Bot controls';

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

export const GLOBAL_BAR_BRAND = 'NOVA';
export const GLOBAL_BAR_NAV_SCANNER = 'Scanner';
export const GLOBAL_BAR_NAV_TRADER = 'Trader';
export const GLOBAL_BAR_NAV_SCANNER_TITLE =
  'Return to the scanner dashboard without closing Trader tape or Level 2';
export const GLOBAL_BAR_NAV_TRADER_TITLE =
  'Open Trader View for the selected symbol, or SPY if none is selected. Use the arrow for QQQ / IWM.';
export const GLOBAL_BAR_NAV_TRADER_DISABLED_TITLE =
  'Select a symbol first, then open Trader View';

export const GLOBAL_BAR_DAY_PNL_LABEL = 'Day P&L';
export const GLOBAL_BAR_NET_LIQ_LABEL = 'Net Liq';
export const GLOBAL_BAR_BP_LABEL = 'BP';
export const GLOBAL_BAR_WORKING_LABEL = 'Working';

/** Only when Gateway / market-data session is down. */
export const GLOBAL_BAR_OFFLINE_CHIP = 'IBKR offline';
/** Gateway up; /api/ibkr/account not ready yet — never use OFFLINE_CHIP here. */
export const GLOBAL_BAR_ACCOUNT_LOADING_CHIP = 'Account…';
/** Gateway up; account poll failed — distinct from session offline. */
export const GLOBAL_BAR_ACCOUNT_UNAVAILABLE_CHIP = 'Account unavailable';
export const GLOBAL_BAR_OFFLINE_PLACEHOLDER = '--';

export const GLOBAL_BAR_CARD_OPEN_PNL = 'Open P&L';
export const GLOBAL_BAR_CARD_REALIZED_PNL = "Day's Realized P&L";
export const GLOBAL_BAR_CARD_CASH = 'Total Cash';
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
export const GLOBAL_BAR_MODE_DISCONNECTED = 'Disconnected';

/** Account + Settings on the shared GlobalAppBar (Scanner + Trader). */
export const GLOBAL_BAR_ACCOUNT_LABEL = 'Account';
export const GLOBAL_BAR_ACCOUNT_TITLE =
  'Account overview — positions, orders, and trading habit reports';
/** IBKR AccountType chip between trade lock and Account (issue #181). */
export const GLOBAL_BAR_ACCOUNT_TYPE_CASH = 'Cash';
export const GLOBAL_BAR_ACCOUNT_TYPE_MARGIN = 'Margin';
export const GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP =
  'Stock shorting requires a margin account. Nova IBKR_SHORT_ENABLED is a separate env gate.';
export const GLOBAL_BAR_ACCOUNT_TYPE_RAW_PREFIX = 'IBKR AccountType:';
export const GLOBAL_BAR_ACCOUNT_TYPE_RAW_MISSING = '(missing)';
export const GLOBAL_BAR_ACCOUNT_TYPE_TRADING_PREFIX = 'IBKR TradingType-S:';
export const GLOBAL_BAR_ACCOUNT_TYPE_ARIA = 'IBKR account type';
export const GLOBAL_BAR_SETTINGS_LABEL = 'Settings';
export const GLOBAL_BAR_SETTINGS_TITLE = 'Open Settings';
