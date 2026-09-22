/**
 * Focus rail state: which scanner list it mirrors and whether it is
 * collapsed, persisted under one versioned localStorage key; and the pure
 * row mapping from the live scanner feed. Lists the feed does not carry are
 * a stated absence, never an empty table.
 */
import { FOCUS_RAIL_DEFAULT_LIST, FOCUS_RAIL_STORAGE_KEY } from '../constantGroups/trader_chrome';
import type { LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';
import { catalystChipLabel, catalystFor, fractionToPercent } from './tabContext';

export const FOCUS_RAIL_STATE_VERSION = 1;

export interface FocusRailState {
  v: typeof FOCUS_RAIL_STATE_VERSION;
  collapsed: boolean;
  list: string;
}

export const FOCUS_RAIL_DEFAULT_STATE: FocusRailState = {
  v: FOCUS_RAIL_STATE_VERSION, collapsed: false, list: FOCUS_RAIL_DEFAULT_LIST,
};

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
  gapPct: number | null;
  /** NEWS / PR, null when the row has no known catalyst. */
  catalyst: string | null;
  headline: string | null;
}

type FeedRows = Pick<LiveScannerFeed, 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'largeCap' | 'catalysts'>;

/** Lists the rail can mirror from the feed it already has; others say so. */
export const FOCUS_RAIL_MIRRORED_LISTS: readonly string[] = [
  'gappers', 'gainers', 'losers', 'afterhours', 'large_cap', 'catalysts',
];

function fromScannerRow(row: ScannerRow, catalysts: readonly Catalyst[]): FocusRow {
  const catalyst = catalystFor(row.symbol, catalysts);
  const gap = row.gap_percent ?? row.change_pct ?? null;
  return {
    symbol: row.symbol.toUpperCase(),
    price: row.price,
    gapPct: fractionToPercent(gap),
    catalyst: catalystChipLabel(catalyst, row),
    headline: catalyst?.catalyst_headline ?? null,
  };
}

function fromCatalyst(row: Catalyst): FocusRow {
  return {
    symbol: row.symbol.toUpperCase(),
    price: row.current_price,
    gapPct: fractionToPercent(row.gap_percent),
    catalyst: catalystChipLabel(row, null),
    headline: row.catalyst_headline,
  };
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
