/**
 * Pure helpers: seed limit/stop from Trade Settings prefs + quote.
 */
import type { TradeDefaultLimitSource } from '../constantGroups/trade_defaults';
import type { ManualOrderSide } from './orderEntry';

export interface QuoteBook {
  last: number | null;
  bid: number | null;
  ask: number | null;
}

function finite(n: number | null | undefined): number | null {
  return n != null && Number.isFinite(n) && n > 0 ? n : null;
}

/** BUY -> ask, SELL -> bid; fall back to last. */
export function seedLimitPrice(
  source: TradeDefaultLimitSource,
  side: ManualOrderSide,
  book: QuoteBook,
): number | null {
  const last = finite(book.last);
  const bid = finite(book.bid);
  const ask = finite(book.ask);

  if (source === 'last') return last;
  if (source === 'mid') {
    if (bid != null && ask != null) return (bid + ask) / 2;
    return last;
  }
  // ask_bid
  if (side === 'BUY') return ask ?? last;
  return bid ?? last;
}

/** Protective stop: BUY below last, SELL above last. */
export function seedStopPrice(
  side: ManualOrderSide,
  last: number | null,
  offsetPct: number,
): number | null {
  const px = finite(last);
  if (px == null) return null;
  const pct = Number.isFinite(offsetPct) && offsetPct >= 0 ? offsetPct : 0;
  const factor = pct / 100;
  const seeded = side === 'BUY' ? px * (1 - factor) : px * (1 + factor);
  return seeded > 0 ? seeded : null;
}

/** Trail $ from the same offset % used for a protective stop. */
export function seedTrailAmount(
  last: number | null,
  offsetPct: number,
): number | null {
  const px = finite(last);
  if (px == null) return null;
  const pct = Number.isFinite(offsetPct) && offsetPct >= 0 ? offsetPct : 0;
  const amount = px * (pct / 100);
  return amount > 0 ? amount : null;
}

export function formatSeedPrice(n: number | null): string {
  if (n == null) return '';
  return n.toFixed(2);
}
