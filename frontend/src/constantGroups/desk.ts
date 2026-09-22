/**
 * Desk -- the Scanner + Trader hybrid (approved UX redesign, 2026-09-21).
 * Every visible string and tunable of the board column lives here. The
 * workspace beside the board is the Trader's own chrome and keeps its labels
 * in constantGroups/trader_chrome.ts.
 */

/* ── Layout ─────────────────────────────────────────────────────────────── */

/** Board column width; the Trader workspace to its right flexes (desk/desk.css). */
export const DESK_BOARD_WIDTH_PX = 640;
/** Below this viewport width the board steps down once so 1440 x 860 has no page scroll. */
export const DESK_BOARD_NARROW_VIEWPORT_PX = 1500;
export const DESK_BOARD_NARROW_WIDTH_PX = 560;

/* ── Board chrome ───────────────────────────────────────────────────────── */

export const DESK_PAGE_TITLE = 'Desk';
export const DESK_BOARD_ARIA = 'Desk board';
export const DESK_BOARD_PICK_ARIA = 'Pick the scanner list the board shows';
export const DESK_BOARD_PICK_TITLE = 'Board list -- any Scanner list, same rows, condensed';
export const DESK_BOARD_OPEN_SCANNER = 'Open on Scanner';
export const DESK_BOARD_OPEN_SCANNER_TITLE = 'Open this list on the Scanner view';
export const DESK_BOARD_NO_FEED = 'No scanner feed in this window';
export const deskBoardNotMirrored = (title: string): string =>
  `${title} is not mirrored on the Desk yet -- open it on the Scanner`;
export const deskBoardEmpty = (title: string): string => `${title}: no rows right now`;
/** Footer: `12 of 41`. */
export const deskBoardCount = (shown: number, total: number): string => `${shown} of ${total}`;
export const deskBoardHiddenByFilter = (count: number): string =>
  `${count} hidden by the exchange filter (Settings > General)`;
/** ADR 008: the Gappers roster stops changing at 09:30; other lists keep moving. */
export const DESK_BOARD_FREEZE_NOTE = 'board freezes at the open';
export const DESK_BOARD_FREEZE_LISTS: readonly string[] = ['gappers'];

/* ── Headline line ──────────────────────────────────────────────────────── */

export const DESK_HEADLINE_NONE = 'no headline';
export const DESK_HEADLINE_NO_ROW =
  'Click a row to open it beside the board · double-click for the full Trader';
export const deskHeadlineTextAbsent = (clock: string): string =>
  `headline at ${clock} · text is not in the scanner feed`;

/* ── Symbol dots + legend ───────────────────────────────────────────────── */

export const DESK_DOT_REC_TITLE = 'Recording';
export const DESK_DOT_BOT_HELD_TITLE = 'Allowlisted · depth line held';
export const DESK_DOT_BOT_QUIET_TITLE = 'Allowlisted · quiet (no depth line)';
export const DESK_LEGEND_REC = 'recording';
export const DESK_LEGEND_BOT_HELD = 'allowlisted, depth line held';
export const DESK_LEGEND_BOT_QUIET = 'allowlisted, quiet';

/* ── Row hover actions (existing capture + bot allowlist calls) ─────────── */

export const DESK_ACTION_RECORD = 'Record';
export const DESK_ACTION_STOP_RECORD = 'Stop rec';
export const DESK_ACTION_ALLOWLIST = 'Allowlist';
export const DESK_ACTION_UNLIST = 'Unlist';
export const DESK_ACTION_RECORD_TITLE = 'Start a Session Record for this symbol';
export const DESK_ACTION_STOP_RECORD_TITLE = 'Stop recording this symbol';
export const DESK_ACTION_ALLOWLIST_TITLE = 'Let the bot act on this symbol';
export const DESK_ACTION_UNLIST_TITLE = 'Remove this symbol from the bot allowlist';

/* ── Cells ──────────────────────────────────────────────────────────────── */

export const DESK_CELL_ABSENT = '—';
export const DESK_STATE_ABSENT_TITLE =
  'Halt state is not carried by the scanner rows; the Level 2 halt chip on the open tab is the live source';
export const DESK_ROW_TITLE = 'Click: open beside the board · Double-click: open in the full Trader';
export const DESK_REL_VOL_SUFFIX = '×';

/**
 * Board columns: [key, label]. Keys are ScannerRow fields or board-only keys;
 * every one declares a width role in components/scannerTableCol.ts and a
 * pinned width in desk/deskBoard.css (issue #276 lock, compact set).
 */
export const DESK_BOARD_COLUMNS: [string, string][] = [
  ['symbol', 'Symbol'],
  ['price', 'Price'],
  ['gap_percent', 'Gap %'],
  ['volume', 'Vol'],
  ['rel_volume', 'Rel vol'],
  ['float', 'Float'],
  ['catalyst', 'Catalyst'],
  ['state', 'State'],
];
/** The one column that absorbs leftover width; every other one is pinned. */
export const DESK_BOARD_FLEX_COLUMN = 'state';

/* ── Workspace area with no tab yet ─────────────────────────────────────── */

export const DESK_WORKSPACE_EMPTY_TITLE = 'No symbol open';
export const DESK_WORKSPACE_EMPTY_HINT =
  'Click a board row: it opens here as a tab -- the same tab the Trader shows.';

export const DESK_SAMPLE_UNAVAILABLE = 'Desk is not available in Sample Data mode.';

/* ── Persisted board list ───────────────────────────────────────────────── */

/** Owner: desk/deskBoardState.ts. Invalidation: `v` bump; older shapes are ignored. */
export const DESK_BOARD_STORAGE_KEY = 'nova.desk.board.v1';
export const DESK_BOARD_DEFAULT_LIST = 'gappers';
