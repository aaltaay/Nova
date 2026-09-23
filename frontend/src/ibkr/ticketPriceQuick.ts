/**
 * Bid / Mid / Ask quick-set for the compact ticket's price field. Reads the
 * live top of book the desk already publishes (`TopOfBookContext`, fed by the
 * Level 2 ladder); a book for another symbol, or one missing a side, yields
 * null so the button greys out with its reason instead of substituting last
 * trade. The ticket keeps following the chosen side (`useTicketPriceFollow`).
 */
import type { TradeDefaultLimitSource } from '../constantGroups/trade_defaults';
import type { TopOfBookLike } from './applyTicketDefaults';
import type { ManualOrderSide, ManualOrderType } from './orderEntry';
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

/**
 * The book side a Settings > Trade limit seed reads, so a Limit ticket seeded
 * from the book keeps following it: Ask / Bid is the ask for a buy and the bid
 * for a sell, Mid the mid, Last nothing. A stop-limit's limit belongs to its
 * stop, never the current book, so only a plain Limit follows by default.
 */
export function followKindForSeed(
  source: TradeDefaultLimitSource,
  side: ManualOrderSide,
  orderType: ManualOrderType,
): QuickPriceKind | null {
  if (orderType !== 'LMT' || source === 'last') return null;
  if (source === 'mid') return 'mid';
  return side === 'BUY' ? 'ask' : 'bid';
}
