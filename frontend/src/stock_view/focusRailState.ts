/**
 * Focus rail state: which scanner lists its two halves mirror, how each is
 * sorted, whether the lower half is folded and the rail collapsed, persisted
 * under one versioned localStorage key; and the pure row mapping from the
 * live scanner feed. Lists the feed does not carry are a stated absence,
 * never an empty table.
 */
import {
  FOCUS_RAIL_DEFAULT_LIST, FOCUS_RAIL_DEFAULT_LOWER_LIST, FOCUS_RAIL_STORAGE_KEY,
} from '../constantGroups/trader_chrome';
import type { LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { Catalyst } from '../types/catalyst';
import type { CatalystVerdict } from '../types/catalystVerdict';
import type { ScannerRow } from '../types/scanner';
import { parseFocusSort, type FocusSort } from './focusRailSort';
import { catalystFor, fractionToPercent, scannerChangePct, scannerRowFor } from './tabContext';

export const FOCUS_RAIL_STATE_VERSION = 1;

/** One half of the rail: the list it mirrors and its column sort. */
export interface FocusPaneState {
  list: string;
  /** Column sort the operator chose; null is the list's own order. */
  sort: FocusSort | null;
}

/** The lower half (operator ask 2026-09-24), which can fold to its header. */
export interface FocusLowerState extends FocusPaneState {
  folded: boolean;
}

export interface FocusRailState {
  v: typeof FOCUS_RAIL_STATE_VERSION;
  collapsed: boolean;
  /** The upper half's list and sort. */
  list: string;
  /** Optional on disk (older v1 files have none), so the version does not change. */
  sort: FocusSort | null;
  /** Optional on disk like `sort`: a file from before the split reads the default. */
  lower: FocusLowerState;
}

export const FOCUS_RAIL_DEFAULT_LOWER: FocusLowerState = {
  list: FOCUS_RAIL_DEFAULT_LOWER_LIST, sort: null, folded: false,
};

export const FOCUS_RAIL_DEFAULT_STATE: FocusRailState = {
  v: FOCUS_RAIL_STATE_VERSION, collapsed: false, list: FOCUS_RAIL_DEFAULT_LIST, sort: null,
  lower: FOCUS_RAIL_DEFAULT_LOWER,
};

/** A persisted lower half, or the default when it is missing or malformed. */
function parseLower(value: unknown): FocusLowerState {
  if (!value || typeof value !== 'object') return FOCUS_RAIL_DEFAULT_LOWER;
  const { list, sort, folded } = value as Partial<FocusLowerState>;
  return {
    list: typeof list === 'string' && list ? list : FOCUS_RAIL_DEFAULT_LOWER_LIST,
    sort: parseFocusSort(sort),
    folded: folded === true,
  };
}

export function readFocusRailState(storage: Pick<Storage, 'getItem'> | null = safeStorage()): FocusRailState {
  try {
    const raw = storage?.getItem(FOCUS_RAIL_STORAGE_KEY);
    if (!raw) return FOCUS_RAIL_DEFAULT_STATE;
    const parsed = JSON.parse(raw) as Partial<FocusRailState> | null;
    if (!parsed || parsed.v !== FOCUS_RAIL_STATE_VERSION) return FOCUS_RAIL_DEFAULT_STATE;
    return {
      v: FOCUS_RAIL_STATE_VERSION,
      collapsed: parsed.collapsed === true,
      list: typeof parsed.list === 'string' && parsed.list ? parsed.list : FOCUS_RAIL_DEFAULT_LIST,
      sort: parseFocusSort(parsed.sort),
      lower: parseLower(parsed.lower),
    };
  } catch {
    return FOCUS_RAIL_DEFAULT_STATE;
  }
}

export function writeFocusRailState(state: FocusRailState, storage: Pick<Storage, 'setItem'> | null = safeStorage()): void {
  try {
    storage?.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({ ...state, v: FOCUS_RAIL_STATE_VERSION }));
  } catch {
    /* private mode: the rail still works, it just forgets */
  }
}

/**
 * Where a Focus rail keeps its state. The Trader's rail reads and writes the
 * operator's saved one; the sample desk's (#449) keeps its own in memory.
 */
export interface FocusRailStore {
  read: () => FocusRailState;
  write: (state: FocusRailState) => void;
}

export const SAVED_FOCUS_RAIL_STORE: FocusRailStore = {
  read: () => readFocusRailState(),
  write: (state) => writeFocusRailState(state),
};

/** A rail state that lives as long as the store: `seed` first, then whatever the rail writes. */
export function memoryFocusRailStore(seed: Partial<FocusRailState> = {}): FocusRailStore {
  let state: FocusRailState = { ...FOCUS_RAIL_DEFAULT_STATE, ...seed, v: FOCUS_RAIL_STATE_VERSION };
  return {
    read: () => state,
    write: (next) => {
      state = next;
    },
  };
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export interface FocusRow {
  symbol: string;
  price: number | null;
  /** The Scanner's %: the price against the prior close, in percent points. */
  changePct: number | null;
  /** The newest headline's time, for the scanner's age circle. */
  headlineAt: string | null;
  /** The row's catalyst verdict (ADR 024); `undefined` when the row carries
   * none, so the circle falls back to the headline's age like the Scanner's. */
  verdict?: CatalystVerdict | null;
  /** True when the desk knows this symbol's news; false when it does not
   * (a watched symbol no list carries), whose news cell stays blank (unknown, not "none"). */
  newsKnown: boolean;
}

type FeedRows = Pick<LiveScannerFeed, 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'largeCap' | 'catalysts'>
  & { tableMeta?: LiveScannerFeed['tableMeta'] };

/** Lists fed by the HOD Momo stream the app shell keeps open for every view. */
export const FOCUS_RAIL_HOD_LISTS = ['hod_momo', 'running_up'] as const;
export type FocusRailHodList = (typeof FOCUS_RAIL_HOD_LISTS)[number];

export function isHodFocusList(list: string): list is FocusRailHodList {
  return (FOCUS_RAIL_HOD_LISTS as readonly string[]).includes(list);
}

/** The operator's watch list (watch_list/) -- the rail's one hand-picked list. */
export const FOCUS_RAIL_WATCH_LIST = 'watch_list';

/** Lists the rail can mirror from what the workspace already holds; others say so. */
export const FOCUS_RAIL_MIRRORED_LISTS: readonly string[] = [
  'gappers', 'gainers', 'losers', 'afterhours', 'large_cap', 'catalysts', ...FOCUS_RAIL_HOD_LISTS,
  FOCUS_RAIL_WATCH_LIST,
];

/** The list a pick from `requested` moves the rail to, or null to stay put:
 * only a list the rail mirrors, so an open from the Watchlist or Earnings
 * never swaps a working list for a "not mirrored" notice. */
export function followedFocusList(requested: string | null): string | null {
  return requested && FOCUS_RAIL_MIRRORED_LISTS.includes(requested) ? requested : null;
}

/**
 * Where a pick from `requested` lands, as a state patch, or null to stay put.
 * A half already showing the list keeps both halves as they are; a HOD /
 * Running Up pick moves the lower half while it shows the other HOD list;
 * anything else moves the upper half. A folded lower half is out of sight,
 * so the upper half follows as the single rail did.
 */
export function routeFocusList(state: FocusRailState, requested: string | null): Partial<FocusRailState> | null {
  const list = followedFocusList(requested);
  if (!list) return null;
  const lowerShown = !state.lower.folded;
  if (state.list === list || (lowerShown && state.lower.list === list)) return null;
  if (lowerShown && isHodFocusList(list) && isHodFocusList(state.lower.list)) {
    return { lower: { ...state.lower, list } };
  }
  return { list };
}

/** The news cell of a row the scanner feed knows: its verdict when it carries
 * one, else the newest headline from the row or the Catalysts list. */
function newsOf(row: ScannerRow | null, catalyst: Catalyst | null): Pick<FocusRow, 'headlineAt' | 'verdict'> {
  const headlineAt = row?.newest_headline_at ?? catalyst?.newest_headline_at ?? null;
  return row && row.catalyst !== undefined ? { headlineAt, verdict: row.catalyst } : { headlineAt };
}

function fromScannerRow(row: ScannerRow, catalysts: readonly Catalyst[]): FocusRow {
  return {
    symbol: row.symbol.toUpperCase(),
    price: row.price,
    changePct: scannerChangePct(row),
    ...newsOf(row, catalystFor(row.symbol, catalysts)),
    newsKnown: true,
  };
}

function fromCatalyst(row: Catalyst): FocusRow {
  return {
    symbol: row.symbol.toUpperCase(),
    price: row.current_price,
    // A Catalysts row carries only its gap_percent (no change_pct).
    changePct: fractionToPercent(row.gap_percent),
    headlineAt: row.newest_headline_at,
    newsKnown: true,
  };
}

/**
 * The operator's watch list, in its own order: each symbol's price, gap and
 * news from the board row that holds it (Large Cap included), else its
 * Catalysts row, else nothing known -- a dash, never an invented figure.
 */
export function watchFocusRows(symbols: readonly string[], feed: FeedRows | null | undefined): FocusRow[] {
  return symbols.map(symbol => {
    const row = scannerRowFor(symbol, feed) ?? feed?.largeCap.find(r => r.symbol.toUpperCase() === symbol) ?? null;
    if (row) return fromScannerRow(row, feed?.catalysts ?? []);
    const catalyst = catalystFor(symbol, feed?.catalysts);
    if (catalyst) return fromCatalyst(catalyst);
    return { symbol, price: null, changePct: null, headlineAt: null, newsKnown: false };
  });
}

/** Rows for a list id; null when the feed does not carry that list here. */
export function focusRowsFor(
  list: string,
  feed: FeedRows | null | undefined,
  filterRows?: <T extends ScannerRow>(rows: T[]) => T[],
): FocusRow[] | null {
  if (!feed) return null;
  const pick = (rows: ScannerRow[]) => (filterRows ? filterRows(rows) : rows).map(row => fromScannerRow(row, feed.catalysts));
  switch (list) {
    case 'gappers': return pick(feed.gappers);
    case 'gainers': return pick(feed.gainers);
    case 'losers': return pick(feed.losers);
    case 'afterhours': return pick(feed.afterhours);
    case 'large_cap': return pick(feed.largeCap);
    case 'catalysts': return feed.catalysts.map(fromCatalyst);
    default: return null;
  }
}

/** Next cursor for ↑ / ↓, clamped; -1 (no cursor) steps onto the first / last row. */
export function stepCursor(cursor: number, delta: 1 | -1, count: number): number {
  if (count <= 0) return -1;
  if (cursor < 0) return delta > 0 ? 0 : count - 1;
  return Math.max(0, Math.min(count - 1, cursor + delta));
}
