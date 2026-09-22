/**
 * The Scanner board's rows after both client-side filters, with every hidden
 * count next to them so the footer can state what is not on screen
 * (single-market-data-feed.mdc: a client-side filter never hides in silence).
 * Order: feed rows -> exchange filter (Settings) -> board chips.
 */
import { useMemo } from 'react';
import type { ScannerRow } from '../types/scanner';
import type { BoardListId } from './boardListForSymbol';
import { BOARD_LIST_SEARCH_ORDER } from './boardListForSymbol';
import type { BoardFilters } from './useBoardFilters';

type ListRows = Record<BoardListId, ScannerRow[]>;
type ListCounts = Record<BoardListId, number>;

export interface BoardRows {
  /** What the board shows. */
  rows: ListRows;
  /** Feed size per list, before any client-side filter. */
  totals: ListCounts;
  hiddenByExchange: ListCounts;
  hiddenByChips: ListCounts;
}

export function useBoardRows(
  feed: ListRows,
  filterByExchange: <T extends { exchange?: string | null }>(rows: T[]) => T[],
  board: BoardFilters,
): BoardRows {
  return useMemo(() => {
    const rows = {} as ListRows;
    const totals = {} as ListCounts;
    const hiddenByExchange = {} as ListCounts;
    const hiddenByChips = {} as ListCounts;
    for (const id of BOARD_LIST_SEARCH_ORDER) {
      const all = feed[id];
      const byExchange = filterByExchange(all);
      const shown = board.filterRows(byExchange);
      rows[id] = shown;
      totals[id] = all.length;
      hiddenByExchange[id] = all.length - byExchange.length;
      hiddenByChips[id] = byExchange.length - shown.length;
    }
    return { rows, totals, hiddenByExchange, hiddenByChips };
  }, [feed, filterByExchange, board]);
}

/** scanAges key for a board list (useScannerData groups gainers + losers as movers). */
export function scanAgeKeyFor(tab: string): 'gappers' | 'movers' | 'afterhours' | 'largeCap' | null {
  switch (tab) {
    case 'gappers': return 'gappers';
    case 'gainers':
    case 'losers': return 'movers';
    case 'afterhours': return 'afterhours';
    case 'large_cap': return 'largeCap';
    default: return null;
  }
}
