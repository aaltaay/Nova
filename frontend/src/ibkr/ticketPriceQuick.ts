/**
 * Bid / Mid / Ask quick-set for the compact ticket's price field. Reads the
 * live top of book the desk already publishes (`TopOfBookContext`); a book
 * for another symbol, or one missing a side, yields null so the button greys
 * out with its reason instead of substituting last trade.
 */
import type { TopOfBookLike } from './applyTicketDefaults';
import { formatSeedPrice } from './tradeDefaultSeed';

export type QuickPriceKind = 'bid' | 'mid' | 'ask';

export const QUICK_PRICE_KINDS: readonly QuickPriceKind[] = ['bid', 'mid', 'ask'];

export function quickPriceFromBook(
  kind: QuickPriceKind,
  book: TopOfBookLike | null | undefined,
  symbol: string,
): string | null {
  if (!book || book.symbol.toUpperCase() !== symbol.trim().toUpperCase()) return null;
  const { bid, ask } = book;
  if (bid == null || ask == null || !(bid > 0) || !(ask > 0)) return null;
  if (kind === 'bid') return formatSeedPrice(bid);
  if (kind === 'ask') return formatSeedPrice(ask);
  return formatSeedPrice((bid + ask) / 2);
}
