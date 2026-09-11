/**
 * Trader View (Stock View) -- tabbed terminal opened by a ticker click.
 * Cap matches backend IBKR_MAX_DEPTH_SYMBOLS (IBKR Level 2 plan limit).
 */

/** Max simultaneous Trader windows/tabs (= concurrent Level 2 streams). */
export const TRADER_MAX_TABS = 3;

/** Index ETFs the operator can pick when opening Trader with no row selected. */
export const TRADER_DEFAULT_SYMBOLS = ['SPY', 'QQQ', 'IWM'] as const;

/** Open this when Trader is clicked with no selected symbol (S&P 500 ETF). */
export const TRADER_DEFAULT_SYMBOL = TRADER_DEFAULT_SYMBOLS[0];

/** Shared ticker hover copy for the replace-active-tab click behavior. */
export const TICKER_OPEN_TRADER_TITLE =
  'Click to open Trader here and replace the active tab.';

/** Row-body hover copy for tables where the ticker (not the row) opens
 * Trader. While Trader is already showing, the row instead switches focus
 * to that symbol's tab -- see selectRowSymbol in useTraderDeskBinding. */
export const ROW_SELECT_QUOTE_TITLE =
  'Click to load this symbol in the Quote Panel. Click the ticker to open Trader.';

export const TRADER_DEFAULTS_TOGGLE_LABEL = 'Index defaults';
export const TRADER_DEFAULTS_MENU_TITLE =
  'Open SPY, QQQ, or IWM as a tab in this window';

/** sessionStorage key for tabs + active symbol in this window. */
export const TRADER_TABS_STORAGE_KEY = 'nova.trader.tabs';

/** sessionStorage key for this OS window's desk id (ADR 011). */
export const TRADER_WINDOW_ID_KEY = 'nova.trader.windowId';

/** sessionStorage key for a pending "at cap" notice after a blocked open. */
export const TRADER_BLOCK_NOTICE_STORAGE_KEY = 'nova.trader.blockNotice';

/** window.open name prefix -- one OS window per symbol (`nova-trader-SPY`). */
export const TRADER_WINDOW_NAME_PREFIX = 'nova-trader';
/** @deprecated Use stockViewWindowName(symbol). Kept as the prefix fallback. */
export const TRADER_WINDOW_NAME = TRADER_WINDOW_NAME_PREFIX;

/** Banner copy when the user tries to open a 4th live Level 2 window/tab. */
export const TRADER_BLOCK_NOTICE_MESSAGE =
  '3 symbols already hold live Level 2 (IBKR plan cap) -- close one or reuse a symbol.';

/** Tab label -- click stays here; double-click extracts. */
export const TRADER_TAB_LABEL_TITLE =
  'Click to view this symbol here. Drag onto another Nova window to dock. Double-click to pop out.';
export const TRADER_TAB_EXTRACT_LABEL = 'Pop out';
export const TRADER_TAB_EXTRACT_TITLE =
  'Open this symbol in a new window. You can also double-click the tab.';
export const TRADER_TAB_EXTRACT_ARIA = 'Open tab in a new window';
export const TRADER_TAB_ADD_TITLE = 'Add a ticker tab in this window';
export const TRADER_TAB_STRIP_HINT =
  'Drag a tab onto another Nova window to dock it. Double-click to pop out.';
export const TRADER_TAB_DOCK_LABEL = 'Dock';
export const TRADER_TAB_DOCK_TITLE =
  'Move this ticker back into the main Nova window';
export const TRADER_TAB_DOCK_ARIA = 'Dock tab into the main window';
export const TRADER_TAB_DRAG_TITLE =
  'Drag onto another Nova window to dock. Double-click to pop out.';
export const TRADER_DOCK_OVERLAY_LABEL = 'Drop to dock this ticker here';
export const TRADER_DOCK_NO_HOST_MESSAGE =
  'Open the main Nova window, then dock this tab onto it.';
export const TRADER_EXTRACT_BLOCKED_MESSAGE =
  'Popup blocked -- allow popups to extract a window, or keep the tab here.';

/**
 * Scanner tables vs account dock vertical split (WID-019 on the discovery desk).
 * Independent of STOCK_VIEW_MAIN_ORDERS_SPLIT_* so Trader chart height stays put.
 */
export const SCANNER_ACCOUNT_DOCK_SPLIT_KEY = 'nova.scanner.accountDockSplitPct';
/** Tables share the column with HOD dock, so the account strip needs more than Trader's 22%. */
export const SCANNER_ACCOUNT_DOCK_SPLIT_PCT = 58;
export const SCANNER_ACCOUNT_DOCK_SPLIT_MIN_PCT = 40;
export const SCANNER_ACCOUNT_DOCK_SPLIT_MAX_PCT = 82;
export const SCANNER_ACCOUNT_DOCK_RESIZE_LABEL = 'Resize scanner tables and Positions';
