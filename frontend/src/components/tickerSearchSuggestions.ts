/**
 * What the bar's ticker search offers under the input: symbols the desk
 * already holds -- open Trader tabs, then positions, then the scanner tables
 * and catalysts -- that start with what was typed. Pure. It never offers a
 * symbol the desk has not seen, and a move the desk does not know stays null.
 */
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import { tabContextFor } from '../stock_view/tabContext';

export type TickerSuggestionSource =
  | 'tab'
  | 'position'
  | 'gappers'
  | 'gainers'
  | 'losers'
  | 'afterhours'
  | 'catalysts';

export interface TickerSuggestion {
  symbol: string;
  source: TickerSuggestionSource;
  /** Signed move in percent points, as the Trader tab prints it; null when unknown. */
  movePct: number | null;
}

export interface TickerSuggestionPools {
  tabs: readonly string[];
  positions: readonly { symbol: string; qty: number }[];
  rows: ScannerDockRows | null;
}

export function normalizeTickerQuery(raw: string): string {
  return raw.trim().toUpperCase();
}

export function tickerSuggestions(
  query: string,
  { tabs, positions, rows }: TickerSuggestionPools,
  limit: number,
): TickerSuggestion[] {
  const q = normalizeTickerQuery(query);
  if (!q) return [];
  const seen = new Set<string>();
  const found: TickerSuggestion[] = [];
  const offer = (raw: string, source: TickerSuggestionSource) => {
    const symbol = normalizeTickerQuery(raw);
    if (!symbol || !symbol.startsWith(q) || seen.has(symbol)) return;
    seen.add(symbol);
    found.push({ symbol, source, movePct: tabContextFor(symbol, rows).gapPct });
  };
  tabs.forEach((symbol) => offer(symbol, 'tab'));
  positions.forEach((p) => { if (p.qty !== 0) offer(p.symbol, 'position'); });
  if (rows) {
    rows.gappers.forEach((r) => offer(r.symbol, 'gappers'));
    rows.gainers.forEach((r) => offer(r.symbol, 'gainers'));
    rows.losers.forEach((r) => offer(r.symbol, 'losers'));
    rows.afterhours.forEach((r) => offer(r.symbol, 'afterhours'));
    rows.catalysts.forEach((r) => offer(r.symbol, 'catalysts'));
  }
  // The exact symbol leads; otherwise the desk's own order (stable sort).
  found.sort((a, b) => Number(b.symbol === q) - Number(a.symbol === q));
  return found.slice(0, limit);
}
