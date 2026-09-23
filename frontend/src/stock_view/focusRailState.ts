/**
 * Focus rail state: which scanner list it mirrors, how it is sorted and
 * whether it is collapsed, persisted under one versioned localStorage key; and the pure
 * row mapping from the live scanner feed. Lists the feed does not carry are
 * a stated absence, never an empty table.
 */
import { FOCUS_RAIL_DEFAULT_LIST, FOCUS_RAIL_STORAGE_KEY } from '../constantGroups/trader_chrome';
import { stripAlertsForMode } from '../hod_momo/hodMomoStripRows';
import { defaultHodMomentumVisibleStrategies } from '../hod_momo/scannerPartition';
import type { AlertObject } from '../hod_momo/types';
import type { LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { Catalyst } from '../types/catalyst';
import type { CatalystVerdict } from '../types/catalystVerdict';
import type { ScannerRow } from '../types/scanner';
import { parseFocusSort, type FocusSort } from './focusRailSort';
import { catalystFor, fractionToPercent, scannerRowFor } from './tabContext';

export const FOCUS_RAIL_STATE_VERSION = 1;

export interface FocusRailState {
  v: typeof FOCUS_RAIL_STATE_VERSION;
  collapsed: boolean;
  list: string;
  /** Column sort the operator chose; null is the list's own order. Optional
   * on disk (older v1 files have none), so the version does not change. */
  sort: FocusSort | null;
}

export const FOCUS_RAIL_DEFAULT_STATE: FocusRailState = {
  v: FOCUS_RAIL_STATE_VERSION, collapsed: false, list: FOCUS_RAIL_DEFAULT_LIST, sort: null,
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
      sort: parseFocusSort(parsed.sort),
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
  /** The newest headline's time, for the scanner's age circle. */
  headlineAt: string | null;
  /** The row's catalyst verdict (ADR 024); `undefined` when the row carries
   * none, so the circle falls back to the headline's age like the Scanner's. */
  verdict?: CatalystVerdict | null;
  /** True when the desk knows this symbol's news; false for a HOD symbol no
   * scanner list carries, whose news cell stays blank (unknown, not "none"). */
  newsKnown: boolean;
}

type FeedRows = Pick<LiveScannerFeed, 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'largeCap' | 'catalysts'>;

/** Lists fed by the HOD Momo stream the app shell keeps open for every view. */
export const FOCUS_RAIL_HOD_LISTS = ['hod_momo', 'running_up'] as const;
export type FocusRailHodList = (typeof FOCUS_RAIL_HOD_LISTS)[number];

export function isHodFocusList(list: string): list is FocusRailHodList {
  return (FOCUS_RAIL_HOD_LISTS as readonly string[]).includes(list);
}

/** Lists the rail can mirror from what the workspace already holds; others say so. */
export const FOCUS_RAIL_MIRRORED_LISTS: readonly string[] = [
  'gappers', 'gainers', 'losers', 'afterhours', 'large_cap', 'catalysts', ...FOCUS_RAIL_HOD_LISTS,
];

/** The list a pick from `requested` moves the rail to, or null to stay put:
 * only a list the rail mirrors, so an open from the Watchlist or Earnings
 * never swaps a working list for a "not mirrored" notice. */
export function followedFocusList(requested: string | null): string | null {
  return requested && FOCUS_RAIL_MIRRORED_LISTS.includes(requested) ? requested : null;
}

/** The news cell of a row the scanner feed knows: its verdict when it carries
 * one, else the newest headline from the row or the Catalysts list. */
function newsOf(row: ScannerRow | null, catalyst: Catalyst | null): Pick<FocusRow, 'headlineAt' | 'verdict'> {
  const headlineAt = row?.newest_headline_at ?? catalyst?.newest_headline_at ?? null;
  return row && row.catalyst !== undefined ? { headlineAt, verdict: row.catalyst } : { headlineAt };
}

function fromScannerRow(row: ScannerRow, catalysts: readonly Catalyst[]): FocusRow {
  const gap = row.gap_percent ?? row.change_pct ?? null;
  return {
    symbol: row.symbol.toUpperCase(),
    price: row.price,
    gapPct: fractionToPercent(gap),
    ...newsOf(row, catalystFor(row.symbol, catalysts)),
    newsKnown: true,
  };
}

function fromCatalyst(row: Catalyst): FocusRow {
  return {
    symbol: row.symbol.toUpperCase(),
    price: row.current_price,
    gapPct: fractionToPercent(row.gap_percent),
    headlineAt: row.newest_headline_at,
    newsKnown: true,
  };
}

function finite(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * HOD Momo / Running Up rows: what the Scanner's strip shows by default
 * (exact duplicates dropped, newest raised first, Former Momo off), one row
 * per ticker from its newest alert. Alerts carry percent points already, so
 * the gap is not converted. They carry no news, so the circle comes from the
 * scanner feed; a symbol no scanner list carries has no known news.
 */
export function hodFocusRows(
  list: FocusRailHodList,
  alerts: readonly AlertObject[],
  feed: FeedRows | null | undefined,
): FocusRow[] {
  const shown = stripAlertsForMode(alerts, list, list === 'hod_momo' ? defaultHodMomentumVisibleStrategies() : null);
  const seen = new Set<string>();
  const rows: FocusRow[] = [];
  for (const alert of shown) {
    const symbol = alert.ticker.trim().toUpperCase();
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    const scannerRow = scannerRowFor(symbol, feed);
    const catalyst = catalystFor(symbol, feed?.catalysts);
    rows.push({
      symbol,
      price: finite(alert.price),
      gapPct: finite(alert.gap_pct) ?? finite(alert.change_pct),
      ...newsOf(scannerRow, catalyst),
      newsKnown: Boolean(scannerRow || catalyst),
    });
  }
  return rows;
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
