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
