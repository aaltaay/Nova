/**
 * Trader View (Stock View) — tabbed terminal opened by double-click.
 * Cap matches backend IBKR_MAX_DEPTH_SYMBOLS (IBKR Level 2 plan limit).
 */

/** Max simultaneous Trader windows/tabs (= concurrent Level 2 streams). */
export const TRADER_MAX_TABS = 3;

/** Index ETFs the operator can pick when opening Trader with no row selected. */
export const TRADER_DEFAULT_SYMBOLS = ['SPY', 'QQQ', 'IWM'] as const;

/** Open this when Trader is clicked with no selected symbol (S&P 500 ETF). */
export const TRADER_DEFAULT_SYMBOL = TRADER_DEFAULT_SYMBOLS[0];

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
