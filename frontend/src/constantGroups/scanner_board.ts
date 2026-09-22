/**
 * Scanner board chrome (approved UX redesign, 2026-09-21): filter chips,
 * saved chip sets, the session line, the footer and row marks. Labels and
 * thresholds only -- the predicates live in scanner/boardFilters.ts.
 *
 * Persisted state (persisted-state.mdc):
 *   owner        scanner/boardFilterPersist.ts
 *   key          SCANNER_BOARD_FILTERS_STORAGE_KEY (utils/prefStore envelope,
 *                schema_version PREF_SCHEMA_VERSION; unknown -> defaults)
 *   invalidation schema bump only; the operator's chips are theirs to keep.
 */

export const SCANNER_BOARD_FILTERS_STORAGE_KEY = 'nova.scanner.board.filters.v1';

// ── Chip thresholds (row fields are what the scanner already carries) ──────
/** `gap_percent` is a fraction on live rows (0.10 = 10%); this is in percent. */
export const SCANNER_CHIP_GAP_MIN_PCT = 10;
/** `float` is shares. */
export const SCANNER_CHIP_FLOAT_MAX_SHARES = 20_000_000;
/** `rel_volume` is a multiple of the average day. */
export const SCANNER_CHIP_RELVOL_MIN = 3;

export const SCANNER_CHIP_IDS = ['gap', 'float', 'relvol', 'news', 'halted'] as const;
export type ScannerChipId = (typeof SCANNER_CHIP_IDS)[number];

export const SCANNER_CHIP_LABEL: Record<ScannerChipId, string> = {
  gap: `Gap ≥ ${SCANNER_CHIP_GAP_MIN_PCT}%`,
  float: `Float ≤ ${SCANNER_CHIP_FLOAT_MAX_SHARES / 1_000_000}M`,
  relvol: `Rel vol ≥ ${SCANNER_CHIP_RELVOL_MIN}`,
  news: 'Has news',
  halted: 'Halted',
};

export const SCANNER_CHIP_TITLE: Record<ScannerChipId, string> = {
  gap: `Keep rows whose gap vs prior close is at least ${SCANNER_CHIP_GAP_MIN_PCT}% (a row with no gap yet is kept)`,
  float: `Keep rows whose reported float is at most ${SCANNER_CHIP_FLOAT_MAX_SHARES / 1_000_000}M shares (unreported float is kept)`,
  relvol: `Keep rows whose relative volume is at least ${SCANNER_CHIP_RELVOL_MIN}x (unreported RVOL is kept)`,
  news: 'Keep rows with at least one headline today',
  halted: 'Halt state is not carried on scanner rows yet -- the Trader Level 2 header shows it. This chip cannot filter.',
};

/** Chips that cannot filter today because the row carries no such fact. */
export const SCANNER_CHIP_UNAVAILABLE: readonly ScannerChipId[] = ['halted'];

export const SCANNER_SAVED_LABEL = 'Saved:';
export const SCANNER_SAVED_NONE = 'none';
export const SCANNER_SAVED_CUSTOM = 'custom';
export const SCANNER_SAVED_MENU_TITLE = 'Named chip sets';
export const SCANNER_SAVED_SAVE_AS = 'Save current as…';
export const SCANNER_SAVED_PROMPT_TITLE = 'Save the current chips as';
export const SCANNER_SAVED_PROMPT_MESSAGE = 'A name for this chip set (existing name replaces it).';
export const SCANNER_SAVED_DELETE_TITLE = 'Forget this set';
export const SCANNER_SAVED_EMPTY = 'No saved sets yet';
export const SCANNER_SAVED_MAX_SETS = 20;

// ── Session line ───────────────────────────────────────────────────────────
export const SCANNER_SESSION_OPENS_IN = 'Opens in';
export const SCANNER_SESSION_CLOSES_IN = 'Closes in';
export const SCANNER_SESSION_AFTER_HOURS = 'After hours';
export const SCANNER_SESSION_SCANNED_PREFIX = 'Scanned';
export const SCANNER_SESSION_SCANNED_SUFFIX = 'ago';
export const SCANNER_SESSION_NOT_SCANNED = 'Not scanned yet';
export const SCANNER_SESSION_TICK_MS = 1000;
export const SCANNER_SESSION_TITLE =
  'Eastern session clock (weekday 09:30-16:00). Holidays are not known here; a holiday counts down to a closed open.';
/** The history-date picker leads the session line (moved off the global bar, 2026-09-22). */
export const SCANNER_HISTORY_TODAY_LABEL = 'Today (Live)';
export const SCANNER_HISTORY_SAMPLE_LABEL = 'Sample (fixtures)';
export const SCANNER_HISTORY_SELECT_TITLE = 'Browse historical snapshots';
export const SCANNER_HISTORY_SELECT_ARIA = 'Scanner snapshot date';

// ── Footer ─────────────────────────────────────────────────────────────────
export function scannerFooterMatch(shown: number, total: number, noun: string): string {
  return `${shown} of ${total} ${noun} match`;
}
export function scannerFooterHiddenByChips(hidden: number): string {
  return `${hidden} more hidden by your filters`;
}
export function scannerFooterHiddenByExchange(hidden: number): string {
  return `${hidden} hidden by the exchange filter (Settings › General)`;
}
export const SCANNER_FOOTER_SHOW_ALL = 'Show all';
export const SCANNER_FOOTER_LEGEND_REC = 'recording';
export const SCANNER_FOOTER_LEGEND_BOT_HELD = 'allowlisted, depth line held (bots may fire)';
export const SCANNER_FOOTER_LEGEND_BOT_QUIET = 'allowlisted, no depth line seen here';

// ── Row marks + hover actions ──────────────────────────────────────────────
export const SCANNER_MARK_REC_TITLE = (symbol: string): string => `${symbol} is recording (Session Record holds its depth line)`;
export const SCANNER_MARK_BOT_HELD_TITLE = (symbol: string): string =>
  `${symbol} is allowlisted and this desk reports a held depth line -- a bot may fire`;
export const SCANNER_MARK_BOT_QUIET_TITLE = (symbol: string): string =>
  `${symbol} is allowlisted; no held depth line is known to this window, so bots stay quiet (BOT_NO_DEPTH_LINE)`;
export const SCANNER_ACTION_TRADER = 'Trader ↗';
export const SCANNER_ACTION_TRADER_TITLE = 'Open in Trader';
export const SCANNER_ACTION_RECORD = 'Record';
export const SCANNER_ACTION_STOP_REC = 'Stop rec';
export const SCANNER_ACTION_ALLOWLIST = 'Allowlist';
export const SCANNER_ACTION_ALLOWLISTED = 'Allowlisted ✓';
export const SCANNER_ACTION_ALLOWLISTED_TITLE = 'On the bot allowlist -- click to remove';
export const SCANNER_ACTION_PIN = 'Pin';
export const SCANNER_ACTION_UNPIN = 'Unpin';
export const SCANNER_ACTION_PIN_TITLE = 'Pin this row to the top of the list for this session';
export const SCANNER_ACTION_UNPIN_TITLE = 'Unpin this row';
/** Gap bar width in px at the top row's gap. */
export const SCANNER_GAP_BAR_MAX_PX = 60;

// ── QA batch: Scanner / HOD / desk honesty (2026-09-22) ────────────────────
/** Persistent-authoritative desks re-read the scanner envelope this often (QA C48). */
export const SCANNER_ENVELOPE_POLL_MS = 15_000;
/** A failed scanner REST fetch retries from this delay, doubling up to the max (QA C31). */
export const SCANNER_REST_RETRY_BASE_MS = 2_000;
export const SCANNER_REST_RETRY_MAX_MS = 30_000;
export const SCANNER_EMPTY_FEED_FAILED_HINT =
  'This is a load failure, not an empty market. Nova retries on its own; the rows appear when the route answers.';
/** Closed-session empty copy: the list is empty, so nothing is being "shown" (QA V25). */
export function scannerEmptyClosedCopy(label: string): string {
  return `Market is closed — no ${label} on this list. Scanning resumes with the next session.`;
}
export const SCANNER_SESSION_FEED_FAILED_TITLE = 'A scanner route failed -- Nova is retrying';
/** "Scanned 45s / 12m / 1h 05m ago": seconds only while under this many (QA V27 / C67). */
export const SCANNER_SCANNED_SECONDS_MAX = 90;
/** Minutes up to this many, then hours + minutes. */
export const SCANNER_SCANNED_MINUTES_MAX = 90;

/** Each row's RVOL mark names the average-volume source it divides by (QA C39). */
export type ScannerRvolSourceMark = { badge: string; title: string };
export const SCANNER_RVOL_SOURCE_MARKS: Record<string, ScannerRvolSourceMark> = {
  yfinance: {
    badge: 'yf',
    title: 'Live volume is IBKR L1; relative volume divides it by the yfinance average daily volume (aux).',
  },
  alpaca: {
    badge: 'IEX',
    title:
      'Live volume is IBKR L1; relative volume divides it by an Alpaca IEX daily-bar average (aux). '
      + 'IEX sees only a sliver of consolidated volume, so thin names read high.',
  },
};
export const SCANNER_RVOL_SOURCE_UNREPORTED: ScannerRvolSourceMark = {
  badge: 'avg?',
  title: 'Live volume is IBKR L1; the backend did not report which average volume this relative volume divides by.',
};
export const SCANNER_VOLUME_HEADER_TITLE =
  'Volume · RVOL: live volume is IBKR L1; relative volume divides it by an average daily volume, and each '
  + "row's mark names the source (yf = yfinance, IEX = Alpaca IEX daily bars). Study vs tape before trusting.";
/** A narrow icon column keeps a short header; the th title carries the full name. */
export const SCANNER_HEADER_SHORT_LABEL: Record<string, string> = {
  earnings_day_offset: 'Earn',
  volume: 'Vol·RVOL',
  short_interest: 'Short',
};
/** A missing figure is a muted dash, never a red "N/A" (QA V21 / C67). */
export const SCANNER_CELL_ABSENT = '—';
export const SCANNER_PRICE_CLOSE_TAG = 'close';
export const SCANNER_PRICE_CLOSE_TITLE =
  "IBKR's prior close -- no trade has printed yet, so this is not a live price";
export const SCANNER_CHANGE_CLOSE_TITLE = 'No trade yet -- a change against the prior close would be invented';

// ── QA pass two (2026-09-22): Scanner / header / layout batch ────────────
/** W12: a gap measured from IB's prior close (no print yet) is invented too. */
export const SCANNER_GAP_CLOSE_TITLE = 'No trade yet -- a gap measured from the prior close would be invented';
/** D10: a mirrored list (Desk board, Focus rail) whose feed is pending or failing. */
export const listFeedLoading = (title: string): string => `${title}: waiting for the scanner feed…`;
export const listFeedFailed = (title: string, error: string): string => `${title}: ${error}`;

// ── Quote Panel look-up (QA V36, operator decision 2026-09-22) ────────────
/**
 * Two symbol doors on the Scanner: the global bar's search opens the Trader,
 * the side panel's look-up loads the Quote Panel in place. The side panel's
 * button and accessible name say where the symbol goes, so the two never read
 * as the same control.
 */
export const QUOTE_PANEL_LOOKUP_LABEL = 'Quote panel: look up';
export const QUOTE_PANEL_LOOKUP_ARIA = 'Symbol to load in the quote panel on this page';
export const QUOTE_PANEL_LOOKUP_PLACEHOLDER = 'Symbol, e.g. AAPL';

