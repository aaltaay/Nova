/**
 * The stop order that protects the position you hold, from the account's working orders (ADR 048, #778 step
 * 3): a SELL stop under a long, a BUY stop over a short -- the one that triggers first (a long's highest, a
 * short's lowest). The held card judges the trade by it while you have not set a stop of your own for this tab,
 * and says it rests at the broker. Pure; a trailing stop is left out (its stop price is a distance, not a price).
 */

/** The fields of a working order this reads (the account's open orders). */
export interface StopOrderLike {
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: string;
  stop_price?: number | null;
}

const STOP_TYPES: ReadonlySet<string> = new Set(['STP', 'STP LMT']);

export function protectiveStop(orders: readonly StopOrderLike[], symbol: string, qty: number): number | null {
  if (!qty) return null;
  const sym = symbol.trim().toUpperCase();
  const side = qty > 0 ? 'SELL' : 'BUY';
  const prices = orders
    .filter(o => o.symbol.toUpperCase() === sym && o.side === side && STOP_TYPES.has(o.order_type.toUpperCase()))
    .map(o => o.stop_price ?? null)
    .filter((p): p is number => p !== null && Number.isFinite(p) && p > 0);
  if (!prices.length) return null;
  return qty > 0 ? Math.max(...prices) : Math.min(...prices);
}
