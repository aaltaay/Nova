/**
 * Shared single-row GlobalAppBar labels and layout tunables.
 * Mounted once in AppShell so every live page inherits the same chrome.
 */

/** Fixed height of the Webull-style top status row (px). */
export const GLOBAL_APP_BAR_HEIGHT_PX = 40;

/** IBKR account / positions / orders poll interval for the shared provider. */
export const IBKR_ACCOUNT_POLL_MS = 5_000;

export const GLOBAL_BAR_BRAND = 'NOVA';
export const GLOBAL_BAR_NAV_SCANNER = 'Scanner';
export const GLOBAL_BAR_NAV_TRADER = 'Trader';
export const GLOBAL_BAR_NAV_SCANNER_TITLE = 'Return to the scanner dashboard';
export const GLOBAL_BAR_NAV_TRADER_TITLE = 'Open Trader View for the selected symbol';
export const GLOBAL_BAR_NAV_TRADER_DISABLED_TITLE =
  'Select a symbol first, then open Trader View';

export const GLOBAL_BAR_DAY_PNL_LABEL = 'Day P&L';
export const GLOBAL_BAR_NET_LIQ_LABEL = 'Net Liq';
export const GLOBAL_BAR_BP_LABEL = 'BP';
export const GLOBAL_BAR_WORKING_LABEL = 'Working';

export const GLOBAL_BAR_OFFLINE_CHIP = 'IBKR offline';
export const GLOBAL_BAR_OFFLINE_PLACEHOLDER = '--';

export const GLOBAL_BAR_CARD_OPEN_PNL = 'Open P&L';
export const GLOBAL_BAR_CARD_REALIZED_PNL = "Day's Realized P&L";
export const GLOBAL_BAR_CARD_CASH = 'Total Cash';
export const GLOBAL_BAR_CARD_GPV = 'Gross Position Value';
export const GLOBAL_BAR_CARD_WORKING = 'Working Orders';

export const GLOBAL_BAR_MODE_PAPER = 'Paper';
export const GLOBAL_BAR_MODE_LIVE = 'Live';
export const GLOBAL_BAR_MODE_DISCONNECTED = 'Disconnected';
