/**
 * The operator's own watch list (operator ask, 2026-09-23): symbols picked by
 * hand from any ticker row, and a toast whenever one of them alerts on the HOD
 * Momo feed (a HOD Momo strategy or Running Up).
 * Not the ranked Five Pillars list -- that one is "Contenders".
 */

/** localStorage key: `{schema_version: 1, symbols: string[]}`, newest first. */
export const WATCH_LIST_STORAGE_KEY = 'nova.watch.list';
export const WATCH_LIST_SCHEMA_VERSION = 1;
/** A hand-kept list; the cap only stops a runaway writer. */
export const WATCH_LIST_MAX = 200;
/** What a ticker may look like: letters, digits and the class separators IBKR uses (BRK/B, BRK.B). */
export const WATCH_LIST_SYMBOL_RE = /^[A-Z][A-Z0-9./-]{0,11}$/;

export const WATCH_LIST_TITLE = 'Watch list';
export const WATCH_LIST_ADD = 'Add to watch list';
export const WATCH_LIST_REMOVE = 'Remove from watch list';
export const watchListAddLabel = (symbol: string): string => `${WATCH_LIST_ADD} -- ${symbol}`;
export const watchListRemoveLabel = (symbol: string): string => `${WATCH_LIST_REMOVE} -- ${symbol}`;

/** Scanner / Desk row actions. */
export const WATCH_ACTION_WATCH = 'Watch';
export const WATCH_ACTION_WATCHING = 'Watching';
export const WATCH_ACTION_WATCH_TITLE = 'Add to your watch list: a toast whenever it hits HOD Momo or Running Up';
export const WATCH_ACTION_WATCHING_TITLE = 'On your watch list -- click to remove it';
export const watchMarkTitle = (symbol: string): string =>
  `${symbol} is on your watch list: a toast whenever it hits HOD Momo or Running Up`;

/** Toasts: how long one stays after its newest alert (hover holds it), and how many stack. */
export const WATCH_TOAST_TTL_MS = 20_000;
export const WATCH_TOAST_MAX = 4;
/** "hit HOD Momo" once a HOD Momo strategy fired; "is running up" while only Running Up has. */
export const watchToastTitle = (symbol: string, hod: boolean): string =>
  (hod ? `${symbol} hit HOD Momo` : `${symbol} is running up`);
export const watchToastCount = (count: number): string => `${count} alerts`;
export const watchToastOpen = (symbol: string): string => `Open ${symbol}`;
export const WATCH_TOAST_UNWATCH = 'Stop watching';
export const WATCH_TOAST_DISMISS = 'Dismiss';
export const WATCH_TOAST_REGION = 'Watch list alerts';

/** The Watch list tab. */
export const WATCH_LIST_TAB_NOTE =
  'Symbols you picked by hand. Whenever one hits HOD Momo or Running Up, a toast says so on every page. '
  + 'Add one from any ticker row (hover or right-click), the chart menu, or here.';
export const WATCH_LIST_ADD_PLACEHOLDER = 'Add a symbol';
export const WATCH_LIST_ADD_BUTTON = 'Add';
export const WATCH_LIST_ADD_INVALID = 'Not a ticker';
export const WATCH_LIST_EMPTY =
  'Nothing on your watch list yet. Hover a scanner row and press Watch, right-click any ticker, or add one above.';
export const WATCH_LIST_NOT_ON_BOARD = 'Not on a board';
export const WATCH_LIST_NO_HOD_TODAY = 'Not yet today';
export const WATCH_LIST_CELL_ABSENT = '—';
export const watchListRemoveTitle = (symbol: string): string => `Remove ${symbol} from your watch list`;
export const WATCH_LIST_HOD_COLUMN_TITLE =
  'The newest HOD Momo or Running Up alert for the symbol today -- what the toast announces';
