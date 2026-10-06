/** Served halt overlays (#571): no roster admission, market fields or freshness changes. */
import type { ScannerRestSink } from './scannerRestApply';

export type ScannerHaltRow = { symbol: string; halted: boolean | null };

export function normalizeHaltRows(raw: unknown): ScannerHaltRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap(item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    const row = item as Record<string, unknown>;
    if (typeof row.symbol !== 'string' || !row.symbol.trim()) return [];
    if (typeof row.halted !== 'boolean' && row.halted !== null) return [];
    return [{ symbol: row.symbol.trim().toUpperCase(), halted: row.halted }];
  });
}

export function applyScannerHaltPatch<T extends { symbol: string; halted?: boolean | null }>(
  rows: T[], patch: ScannerHaltRow[],
): T[] {
  const bySymbol = new Map(patch.map(row => [row.symbol.trim().toUpperCase(), row.halted]));
  let changed = false;
  const next = rows.map(row => {
    const symbol = row.symbol.toUpperCase();
    if (!bySymbol.has(symbol) || row.halted === bySymbol.get(symbol)) return row;
    changed = true;
    return { ...row, halted: bySymbol.get(symbol)! };
  });
  return changed ? next : rows;
}

export function applyScannerHaltRows(sink: ScannerRestSink, rows: ScannerHaltRow[]): void {
  sink.setGappers(prev => applyScannerHaltPatch(prev, rows));
  sink.setGainers(prev => applyScannerHaltPatch(prev, rows));
  sink.setLosers(prev => applyScannerHaltPatch(prev, rows));
  sink.setAfterhours(prev => applyScannerHaltPatch(prev, rows));
  sink.setLargeCap(prev => applyScannerHaltPatch(prev, rows));
}
