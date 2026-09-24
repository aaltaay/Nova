/**
 * Trader View (Stock View) -- tabbed terminal opened by a ticker click.
 * Live-slot cap matches backend IBKR_MAX_DEPTH_SYMBOLS (IBKR Level 2 plan limit).
 * The tab strip itself is unbounded -- extras stay visible but gray / suspended.
 */

/** Max simultaneous live L2 / full-desk streams in one window. Strip is unbounded. */
export const TRADER_MAX_LIVE_TABS = 3;
/** @deprecated Use TRADER_MAX_LIVE_TABS -- strip length is not capped. */
export const TRADER_MAX_TABS = TRADER_MAX_LIVE_TABS;

/** Index ETFs the operator can pick when opening Trader with no row selected. */
export const TRADER_DEFAULT_SYMBOLS = ['SPY', 'QQQ', 'IWM'] as const;

/** Open this when Trader is clicked with no selected symbol (S&P 500 ETF). */
export const TRADER_DEFAULT_SYMBOL = TRADER_DEFAULT_SYMBOLS[0];

/** Shared ticker hover copy for add-or-activate (never silent-replace). */
export const TICKER_OPEN_TRADER_TITLE =
  'Click to open Trader here -- adds a tab or activates one already open.';

/** Row-body hover copy for tables where the ticker (not the row) opens
 * Trader. While Trader is already showing, the row adds or activates that
 * symbol's tab -- see selectRowSymbol in useTraderDeskBinding. */
export const ROW_SELECT_QUOTE_TITLE =
  'Click to load this symbol in the Quote Panel. Click the ticker to open Trader.';

export const TRADER_DEFAULTS_TOGGLE_LABEL = 'Index defaults';
export const TRADER_DEFAULTS_MENU_TITLE =
  'Open SPY, QQQ, or IWM as a tab in this window';

/** sessionStorage key for tabs + active symbol in this window. */
export const TRADER_TABS_STORAGE_KEY = 'nova.trader.tabs';

/** sessionStorage key for this OS window's desk id (ADR 011). */
export const TRADER_WINDOW_ID_KEY = 'nova.trader.windowId';
/** Marks that a float already reminted its window id (copied sessionStorage from opener). */
export const TRADER_FLOAT_ID_READY_KEY = 'nova.trader.floatIdReady';
/** localStorage: last host desk that can receive a Dock-button request. */
export const TRADER_LAST_HOST_KEY = 'nova.trader.lastHostWindowId';

/** sessionStorage key for a pending "at cap" notice after a blocked open. */
export const TRADER_BLOCK_NOTICE_STORAGE_KEY = 'nova.trader.blockNotice';

/** window.open name prefix -- one OS window per symbol (`nova-trader-SPY`). */
export const TRADER_WINDOW_NAME_PREFIX = 'nova-trader';
/** @deprecated Use stockViewWindowName(symbol). Kept as the prefix fallback. */
export const TRADER_WINDOW_NAME = TRADER_WINDOW_NAME_PREFIX;

/** Banner copy reserved for extract/dock transport failures -- not a 4th-tab hard block. */
export const TRADER_BLOCK_NOTICE_MESSAGE =
  'Could not complete that Trader move. Try again, or dock onto the main Nova window.';
export const TRADER_TAB_SUSPENDED_TITLE =
  'Suspended -- no live Level 2. Click to make this tab live (oldest live tab goes gray).';

/** Tab label -- click stays here; double-click extracts. */
export const TRADER_TAB_LABEL_TITLE =
  'Click to view this symbol here. Drag onto another Nova window to dock. Double-click to pop out.';
export const TRADER_TAB_LABEL_TITLE_FLOAT =
  'Click to view this symbol here. Drag onto the main Nova window to dock.';
export const TRADER_TAB_EXTRACT_LABEL = 'Pop out';
export const TRADER_TAB_EXTRACT_TITLE =
  'Open this symbol in a new window. You can also double-click the tab.';
export const TRADER_TAB_EXTRACT_ARIA = 'Open tab in a new window';
export const TRADER_TAB_ADD_TITLE = 'Add a ticker tab in this window';
/** Why + is locked (ux/whyTip.ts): one new tab at a time. */
export const TRADER_TAB_ADD_DRAFT_OPEN_WHY =
  'A new tab is already open -- type its ticker and press Enter, or Esc to drop it';
export const TRADER_TAB_STRIP_HINT =
  'Drag a tab onto another Nova window to dock it. Double-click to pop out.';
export const TRADER_TAB_STRIP_HINT_FLOAT =
  'Drag this tab onto the main Nova window to dock it.';
/** Preview tabs (ADR 011, 2026-09-22): the unpinned tab is where the next ticker opens. */
export const TRADER_TAB_PREVIEW_TITLE =
  'Preview tab -- the next ticker you open replaces it. Pin it to keep it.';
export const TRADER_TAB_PIN_LABEL = 'Pin tab';
export const TRADER_TAB_UNPIN_LABEL = 'Unpin tab';
export const TRADER_TAB_PIN_TITLE = 'Pin this tab so the next ticker opens beside it, not over it';
export const TRADER_TAB_UNPIN_TITLE = 'Unpin this tab -- the next ticker you open replaces it';
export const TRADER_TAB_PIN_ARIA = 'Pin tab';
export const TRADER_TAB_UNPIN_ARIA = 'Unpin tab';
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

// ── QA pass two (2026-09-22): Scanner / header / layout batch ────────────
/**
 * D10: what a Gateway-bound surface says while `/api/ibkr/status` is pending or
 * failing -- nothing is known about the Gateway then. The depth card and the
 * ticket (trader_chrome.ts) each end the sentence with what waits for it.
 */
export const GATEWAY_STATUS_PENDING = "Checking IB Gateway -- Nova's status has not answered yet";
export const GATEWAY_STATUS_FAILED = "Nova's status request is failing, so IB Gateway's state is unknown";
/** D10: the Stock Quote card's depth hint, by what the status actually knows. */
export const TRADER_DEPTH_CONNECT_GATEWAY = 'Connect IB Gateway for Level 2 and Time & Sales';
export const TRADER_DEPTH_STATUS_PENDING = GATEWAY_STATUS_PENDING;
export const TRADER_DEPTH_STATUS_FAILED = `${GATEWAY_STATUS_FAILED} -- Level 2 and Time & Sales wait for it`;
/**
 * W30: the tab / Focus rail figure is the scanner's gap (price against the
 * prior close); the quote card's Gap% is the opening gap (the open against
 * the prior close), which reads -- until the open prints. Each says which.
 */
export const TRADER_TAB_GAP_TITLE =
  "Scanner gap: the price against the prior close. The quote card's Gap% is the opening gap -- the open against the prior close -- so it reads -- before the open.";
export const QUOTE_GAP_OPEN_TITLE =
  "Opening gap: the day's open against the prior close -- it reads -- until the open prints. The tab's figure is the price against the prior close.";

