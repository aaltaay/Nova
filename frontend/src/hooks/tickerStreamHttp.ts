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

/** WS `initial` must be a real quote. Error-only payloads must not become detail. */
export function tickerDetailFromWsInitial(
  msg: unknown,
  symbol: string,
): TickerDetail | null {
  if (!msg || typeof msg !== 'object') return null;
  const row = msg as { type?: unknown };
  if (row.type !== 'initial') return null;
  const { type: _type, ...data } = row as Record<string, unknown>;
  return tickerDetailFromHttp(data, symbol);
}
