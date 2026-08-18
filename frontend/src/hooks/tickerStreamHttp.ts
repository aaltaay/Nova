/** Map GET /api/ticker/{symbol} onto the WS `initial` shape. */
import type { TickerDetail } from '../types/ticker';

export function tickerDetailFromHttp(
  data: unknown,
  symbol: string,
): TickerDetail | null {
  if (!data || typeof data !== 'object') return null;
  const row = data as TickerDetail & { error?: unknown };
  if (typeof row.symbol !== 'string') return null;
  if (row.symbol.toUpperCase() !== symbol.toUpperCase()) return null;
  if (row.error && row.snapshot == null) return null;
  if (!row.snapshot || typeof row.snapshot !== 'object') return null;
  return row;
}
