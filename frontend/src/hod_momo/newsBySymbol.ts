/**
 * Build symbol -> newest_headline_at map from scanner / catalyst rows.
 * Pure helper for HOD News flame join (display-time only).
 */

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
