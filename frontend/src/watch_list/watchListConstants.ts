/**
 * The watch list, which is today's hot list since ADR 044 ("the watch list folds
 * into the ★"): symbols starred by hand from any ticker row or put on by the
 * leaders rule. Its toasts (ADR 044 amendment, 2026-10-12: "i get alot of stupid
 * toast notifications"): a star toasts on a HOD Momo strategy (never Running Up)
 * and on its setups from armed up, an auto star once when it joins, only inside
 * the trading window, and a stock's alerts stay quiet a while after its toast.
 * Nova scores every toast it raised.
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
  'Star it onto today\'s hot list: the scanners follow it all day, and a toast when it hits HOD Momo or a setup on '
  + 'it arms, comes near or triggers. A star never lets the bot trade it: that is its Buy / Sell (Who trades)';
export const WATCH_ACTION_WATCHING_TITLE = 'On today\'s hot list -- click to take it off';
/** The mark beside a listed ticker: ★ your star, ☆ an auto star (the top of the Gainers board). */
export const watchMarkTitle = (symbol: string, how: 'star' | 'auto' = 'star'): string =>
  (how === 'auto'
    ? `${symbol} was auto-starred onto today's hot list (the top of the Gainers board, 07:00-16:00 ET)`
    : `${symbol} is on today's hot list: your star`)
  + (how === 'auto'
    ? ': the scanners follow it all day, and one toast when it joined. Star it for its HOD Momo and setup toasts. '
    : ': the scanners follow it all day, and a toast when it hits HOD Momo or a setup on it arms, comes near or '
      + 'triggers. ')
  + 'Watching only: the bot trades it only where its Buy / Sell says Bot';

/** Toasts: how long one stays after its newest raised event (hover holds it), and how many stack. */
export const WATCH_TOAST_TTL_MS = 20_000;
export const WATCH_TOAST_MAX = 4;
export const watchToastTitle = (symbol: string): string => `${symbol} hit HOD Momo`;
export const watchToastCount = (count: number): string => `${count} alerts`;
export const watchToastOpen = (symbol: string): string => `Open ${symbol}`;
export const WATCH_TOAST_UNWATCH = 'Take off the hot list';
export const WATCH_TOAST_STAR = '★ Star it';
export const watchToastStarTitle = (symbol: string): string =>
  `Make ${symbol} your star: then it toasts when it hits HOD Momo or a setup on it arms, comes near or triggers`;
export const WATCH_TOAST_DISMISS = 'Dismiss';
export const WATCH_TOAST_REGION = 'Hot list alerts';

/* ---------- Which toasts come (ADR 044 amendment, operator ask 2026-10-12) ---------- */

/** After a toast, a stock's HOD Momo alerts stay quiet this long; a setup moving up a stage always comes through. */
export const WATCH_TOAST_QUIET_MS = 15 * 60_000;
/** An auto star toasts when it joins only if it joined this recently: a page load never announces old joins. */
export const WATCH_TOAST_JOIN_FRESH_MS = 2 * 60_000;
/** "GIXI joined the top 3 Gainers": an auto star's one toast. `n` is the auto feed's top N (null: unknown). */
export const watchJoinTitle = (symbol: string, n: number | null): string =>
  (n && n > 0 ? `${symbol} joined the top ${n} Gainers` : `${symbol} joined the leaders`);
export const watchJoinRank = (rank: number): string => `#${rank} on the board`;
/** A setup's numbers on its toast. */
export const watchSetupNumbers = (trigger: string, stop: string): string => `Trigger ${trigger} · Stop ${stop}`;

/** The trading window toasts come in, ET (owner toastWindow.ts): `{schema_version: 1, start, end}` "HH:MM". */
export const WATCH_TOAST_WINDOW_KEY = 'nova.watch.toastWindow';
export const WATCH_TOAST_WINDOW_SCHEMA_VERSION = 1;
export const WATCH_TOAST_WINDOW_DEFAULT = { start: '07:00', end: '16:00' } as const;
export const WATCH_TOAST_WINDOW_LABEL = 'Toasts';
export const WATCH_TOAST_WINDOW_TO = 'to';
export const WATCH_TOAST_WINDOW_ET = 'ET';
export const WATCH_TOAST_WINDOW_TIP =
  'No toast comes outside these hours (Eastern). The setup scanner, HOD Momo and this list keep running.';
export const WATCH_TOAST_WINDOW_BAD = 'The end must be after the start';
export const WATCH_TOAST_WINDOW_RESET = 'Default';

/** Nova scores its own toasts (owner toastScores.ts): the day's record in localStorage. */
export const WATCH_TOAST_SCORES_KEY = 'nova.watch.toastScores';
export const WATCH_TOAST_SCORES_SCHEMA_VERSION = 1;
export const WATCH_TOAST_SCORES_MAX = 500;
/** Minutes after the toast's own minute whose close is the outcome. */
export const WATCH_TOAST_SCORE_MINUTES = 5;
/** How often the main desk window looks for toasts ready to score, and when it stops trying one. */
export const WATCH_TOAST_SCORE_POLL_MS = 30_000;
export const WATCH_TOAST_SCORE_GIVE_UP_MS = 30 * 60_000;
/** A toast's minute bar is final this long after its fifth minute closes. */
export const WATCH_TOAST_SCORE_SETTLE_MS = 60_000;
export const WATCH_TOAST_SCORE_TIMEFRAME = '1Min';
export const WATCH_TOAST_SCORE_NO_BARS = 'no bars';

export const WATCH_TOAST_SCORES_TITLE = 'Toasts today';
export const WATCH_TOAST_SCORES_EMPTY = 'No toast yet today.';
export const WATCH_TOAST_SCORES_TIP =
  'Every toast Nova raised today, by kind. Five minutes after a toast Nova reads the 1-minute bars: the close of the '
  + 'fifth minute after the toast\'s own against the price the toast showed (else the close of the minute before it). '
  + 'A score, not a fill.';
export const WATCH_TOAST_KIND_LABELS: Readonly<Record<string, string>> = {
  join: 'Joined the leaders',
  hod: 'Hit HOD Momo',
  armed: 'Setup armed',
  near: 'Setup near its trigger',
  triggered: 'Setup triggered',
};
export const WATCH_TOAST_HELD_LABELS: Readonly<Record<string, string>> = {
  running_up: 'Running Up',
  auto_star: 'auto stars after joining',
  forming: 'setups forming',
  quiet: 'quiet after a toast',
  outside_window: 'outside the window',
};
export const watchToastHeldLine = (parts: readonly string[]): string => `Held back: ${parts.join(' · ')}`;
export const WATCH_TOAST_HELD_TIP =
  'Alerts on the hot list that raised no toast today, and why: Running Up never toasts, an auto star toasts only when '
  + 'it joins, a setup toasts from armed up, a stock is quiet for 15 minutes after its toast unless a setup moves up a '
  + 'stage, and nothing toasts outside the window.';

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
  'Today\'s hot list: the stocks you starred (★) and the ones the leaders rule put on (☆). A ★ toasts when it hits '
  + 'HOD Momo or a setup on it arms, comes near its trigger or triggers; a ☆ toasts once, when it joins. It starts '
  + 'empty at 04:00 ET. Star one from any ticker row (hover or right-click), the chart menu, or here.';
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
  'The newest HOD Momo or Running Up alert for the symbol today. Running Up never toasts; a HOD Momo strategy '
  + 'toasts for a star';
export const WATCH_LIST_SETUP_COLUMN_TITLE =
  "The symbol's most advanced setup on the setup scanner now -- forming, armed, near its trigger, triggered "
  + 'or failed. For a star, a toast says so when one arms, comes near or triggers.';
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
