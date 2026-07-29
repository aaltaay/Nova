/**
 * Trader View (Stock View) — tabbed terminal opened by double-click.
 * Cap matches backend IBKR_MAX_DEPTH_SYMBOLS (IBKR Level 2 plan limit).
 */

/** Max simultaneous Trader tabs (= concurrent Level 2 streams). */
export const TRADER_MAX_TABS = 3;

/** sessionStorage key for tabs + active symbol in this window. */
export const TRADER_TABS_STORAGE_KEY = 'nova.trader.tabs';

/** sessionStorage key for a pending "at cap" notice after a blocked open. */
export const TRADER_BLOCK_NOTICE_STORAGE_KEY = 'nova.trader.blockNotice';

/** Fixed window.open target so all symbols share one Trader OS window. */
export const TRADER_WINDOW_NAME = 'nova-trader';

/** Banner copy when the user tries to open a 4th live Level 2 tab. */
export const TRADER_BLOCK_NOTICE_MESSAGE =
  '3 tabs already hold live Level 2 (IBKR plan cap) -- close a tab or edit one to a new symbol.';
