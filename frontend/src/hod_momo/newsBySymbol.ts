/**
 * Build symbol -> newest_headline_at map from scanner / catalyst rows.
 * Pure helper for HOD News flame join (display-time only).
 */
import type { CatalystVerdict } from '../types/catalystVerdict';

export function buildNewsBySymbol(
  rows: Array<{ symbol: string; newest_headline_at: string | null }>,
): Map<string, string> {
  const out = new Map<string, string>();
  for (const row of rows) {
    const sym = (row.symbol || '').trim().toUpperCase();
    const at = row.newest_headline_at;
    if (!sym || !at) continue;
    const prev = out.get(sym);
    if (!prev || at > prev) out.set(sym, at);
  }
  return out;
}

/**
 * Symbol -> catalyst verdict (ADR 024) from the rows that carry one. A read verdict beats an unread
 * (null) one for the same symbol; rows without the field add nothing, so HOD keeps the headline flame.
 */
export function buildCatalystBySymbol(
  rows: Array<{ symbol: string; catalyst?: CatalystVerdict | null }>,
): Map<string, CatalystVerdict | null> {
  const out = new Map<string, CatalystVerdict | null>();
  for (const row of rows) {
    if (row.catalyst === undefined) continue;
    const sym = (row.symbol || '').trim().toUpperCase();
    if (!sym) continue;
    if (!out.get(sym)) out.set(sym, row.catalyst);
  }
  return out;
}
