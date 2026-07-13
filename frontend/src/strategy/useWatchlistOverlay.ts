/**
 * Joins the already-polled /api/strategy/watchlist entries onto Gappers/Movers/
 * After Hours scanner rows by symbol, so the scanner tables can show Five Pillars
 * + composite score without re-scoring anything on the client. Read-only join —
 * does not call any new API and does not touch the Watchlist tab itself.
 */
import { useMemo } from 'react';
import type { ScannerRow } from '../types/scanner';
import type { WatchlistEntry } from './types';

export function useWatchlistOverlay<T extends ScannerRow>(
  rows: T[],
  watchlistEntries: WatchlistEntry[],
): T[] {
  const bySymbol = useMemo(() => {
    const map = new Map<string, WatchlistEntry>();
    for (const entry of watchlistEntries) map.set(entry.symbol, entry);
    return map;
  }, [watchlistEntries]);

  return useMemo(
    () =>
      rows.map(row => {
        const entry = bySymbol.get(row.symbol) ?? null;
        return { ...row, watchlist: entry, watchlist_score: entry?.composite_score ?? null };
      }),
    [rows, bySymbol],
  );
}
