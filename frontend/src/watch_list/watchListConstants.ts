/**
 * The watch list, which is today's hot list since ADR 044 ("the watch list folds
 * into the ★"): symbols starred by hand from any ticker row or put on by the
 * leaders rule, and a toast whenever one of them alerts on the HOD
 * Momo feed (a HOD Momo strategy or Running Up) or one of its setups climbs its
 * ladder on the setup scanner -- forming, armed, near, triggered (operator ask,
 * 2026-09-24: "shouldn't these toast notifications be watching if a strategy is
 * forming?").
 * Not the ranked Five Pillars list -- that one is "Contenders".
 */
import type { WatchSetupStage } from './types';

/** The list this desk kept before the hot list (read only now): `{schema_version: 1, symbols: string[]}`. */
export const WATCH_LIST_STORAGE_KEY = 'nova.watch.list';
export const WATCH_LIST_SCHEMA_VERSION = 1;
/** A hand-kept list; the cap only stops a runaway writer. */
export const WATCH_LIST_MAX = 200;
/** What a ticker may look like: letters, digits and the class separators IBKR uses (BRK/B, BRK.B). */
export const WATCH_LIST_SYMBOL_RE = /^[A-Z][A-Z0-9./-]{0,11}$/;

export const WATCH_LIST_TITLE = 'Hot list';
export const WATCH_LIST_ADD = '★ Add to today\'s hot list';
export const WATCH_LIST_REMOVE = 'Take off today\'s hot list';
export const watchListAddLabel = (symbol: string): string => `${WATCH_LIST_ADD} -- ${symbol}`;
export const watchListRemoveLabel = (symbol: string): string => `${WATCH_LIST_REMOVE} -- ${symbol}`;

/** Scanner / Desk row actions. */
export const WATCH_ACTION_WATCH = '★';
export const WATCH_ACTION_WATCHING = '★ Listed';
export const WATCH_ACTION_WATCH_TITLE =
  'Star it onto today\'s hot list: the scanners follow it all day, and a toast whenever it hits HOD Momo or Running '
  + 'Up or a setup forms on it. A star never lets the bot trade it: that is its Buy / Sell (Who trades)';
export const WATCH_ACTION_WATCHING_TITLE = 'On today\'s hot list -- click to take it off';
/** The mark beside a listed ticker: ★ your star, ☆ an auto star (the top of the Gainers board). */
export const watchMarkTitle = (symbol: string, how: 'star' | 'auto' = 'star'): string =>
  (how === 'auto'
    ? `${symbol} was auto-starred onto today's hot list (the top of the Gainers board, 07:00-16:00 ET)`
    : `${symbol} is on today's hot list: your star`)
  + ': the scanners follow it all day, and a toast whenever it hits HOD Momo or Running Up, or a setup forms on it. '
  + 'Watching only: the bot trades it only where its Buy / Sell says Bot';

/** Toasts: how long one stays after its newest alert (hover holds it), and how many stack. */
export const WATCH_TOAST_TTL_MS = 20_000;
export const WATCH_TOAST_MAX = 4;
/** "hit HOD Momo" once a HOD Momo strategy fired; "is running up" while only Running Up has. */
export const watchToastTitle = (symbol: string, hod: boolean): string =>
  (hod ? `${symbol} hit HOD Momo` : `${symbol} is running up`);
export const watchToastCount = (count: number): string => `${count} alerts`;
export const watchToastOpen = (symbol: string): string => `Open ${symbol}`;
export const WATCH_TOAST_UNWATCH = 'Take off the hot list';
export const WATCH_TOAST_DISMISS = 'Dismiss';
export const WATCH_TOAST_REGION = 'Hot list alerts';

/* ---------- Setups on watched symbols (operator ask, 2026-09-24) ---------- */

/** A setup forming again on the same symbol (a fail, then a fresh leg) toasts at most this often. */
export const WATCH_SETUP_FORMING_REPEAT_MS = 5 * 60_000;
/**
 * The title a setup's climb gives the toast: "PFSA: bull flag armed". `setup` is
 * the setup's name ("bull flag", "second pullback"); `level` what its trigger is
 * ("trigger", or the open / the high).
 */
export const watchSetupTitle = (symbol: string, setup: string, stage: WatchSetupStage, level: string): string => {
  switch (stage) {
    case 'forming': return `${symbol}: ${setup} forming`;
    case 'armed': return `${symbol}: ${setup} armed`;
    case 'near': return `${symbol}: ${setup} near the ${level}`;
    default: return `${symbol}: ${setup} triggered`;
  }
};
/** A setup line whose setup the board no longer lists. */
export const WATCH_SETUP_UNLISTED = 'Off the board';
export const WATCH_SETUP_UNLISTED_DETAIL =
  'The setup scanner no longer lists it: back to watching, or no longer one of the names it follows.';
export const watchSetupLast = (price: string): string => `Last ${price}`;

/** The Hot list tab (the watch list, ADR 044). */
export const WATCH_LIST_TAB_NOTE =
  'Today\'s hot list: the stocks you starred and the ones the leaders rule put on. Whenever one hits HOD Momo or '
  + 'Running Up, or a setup forms, arms, comes near its trigger or triggers on it, a toast says so on every page. '
  + 'It starts empty at 04:00 ET. Star one from any ticker row (hover or right-click), the chart menu, or here.';
export const WATCH_LIST_ADD_PLACEHOLDER = 'Star a symbol';
export const WATCH_LIST_ADD_BUTTON = '★ Add';
export const WATCH_LIST_ADD_INVALID = 'Not a ticker';
export const WATCH_LIST_EMPTY =
  'Nothing on today\'s hot list yet. Hover a scanner row and press ★, right-click any ticker, or add one above.';
/** The list this desk kept before the hot list: offered once, then forgotten. */
export const watchListSavedNote = (n: number, room: number): string =>
  `Your watch list from before the hot list has ${n} name${n === 1 ? '' : 's'}. `
  + (room > 0 ? `Star ${Math.min(n, room)} of them onto today's list (room for ${room}), or forget it.`
    : 'Today\'s list is full: take some off first, or forget it.');
export const WATCH_LIST_SAVED_STAR = '★ Star them';
export const WATCH_LIST_SAVED_FORGET = 'Forget it';
export const WATCH_LIST_NOT_ON_BOARD = 'Not on a board';
export const WATCH_LIST_NO_HOD_TODAY = 'Not yet today';
export const WATCH_LIST_CELL_ABSENT = '—';
export const watchListRemoveTitle = (symbol: string): string => `Take ${symbol} off today's hot list`;
export const WATCH_LIST_HOD_COLUMN_TITLE =
  'The newest HOD Momo or Running Up alert for the symbol today -- what the toast announces';
export const WATCH_LIST_SETUP_COLUMN_TITLE =
  "The symbol's most advanced setup on the setup scanner now -- forming, armed, near its trigger, triggered "
  + 'or failed. A toast says so each time one climbs.';
export const WATCH_LIST_SETUP_NOTHING = 'Nothing forming';
export const watchListSetupNothingTip = (symbol: string): string =>
  `The setup scanner follows ${symbol}, and no setup is forming, armed or near on it now.`;
export const WATCH_LIST_SETUP_NOT_FOLLOWED = 'Not followed';
export const watchListSetupNotFollowedTip = (symbol: string): string =>
  `The setup scanner follows the HOD Momo names only (Gappers, Gainers, After Hours and Former Momo, `
  + `40 at most). ${symbol} is not one of them now, so no setup can form on it and no setup toast comes.`;
export const WATCH_LIST_SETUP_UNKNOWN_TIP =
  'The backend is running code from before the setup scanner named the symbols it follows, so Nova cannot tell: '
  + 'nothing forming, or not followed at all. Reload it (gear → Reload backend) to see which.';
export const WATCH_LIST_SETUP_OFFLINE_TIP =
  "The setup scanner's live board is not here now (not connected, or the Sim replay is on the board).";
export const watchListSetupAlso = (lines: readonly string[]): string => `Also: ${lines.join(' · ')}`;
