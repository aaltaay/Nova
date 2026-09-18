/**
 * Apply Settings > Trade > Stocks prefs onto a fresh ManualOrderTicket.
 */
import {
  forcedManualOrderQty,
  usesLimitPrice,
  usesStopPrice,
} from './orderEntry';
import type { ManualOrderSide, ManualOrderType } from './orderEntry';
import { readTradeDefaultsPrefs } from '../settings/tradeDefaultsPrefs';
import {
  formatSeedPrice,
  seedLimitPrice,
  seedStopPrice,
  seedTrailAmount,
} from './tradeDefaultSeed';

export interface TopOfBookLike {
  symbol: string;
  bid: number | null;
  ask: number | null;
}

/**
 * Share count a fresh ticket starts on: forced override, else Settings > Trade.
 * Shared with the chart context menu so its "Buy SYM 100" label cannot drift
 * from the qty the ticket actually receives.
 */
export function defaultTicketQty(): string {
  const forced = forcedManualOrderQty();
  return String(forced ?? readTradeDefaultsPrefs().quantity);
}

export function applyTicketDefaults(
  symbolKey: string,
  referencePrice: number | null,
  topOfBook: TopOfBookLike | null,
): {
  orderType: ManualOrderType;
  quantityValue: string;
  limitPrice: string;
  stopPrice: string;
  outsideRth: boolean;
  side: ManualOrderSide;
} {
  const prefs = readTradeDefaultsPrefs();
  const side: ManualOrderSide = 'BUY';
  const book =
    topOfBook && topOfBook.symbol.toUpperCase() === symbolKey.toUpperCase()
      ? {
          last: referencePrice,
          bid: topOfBook.bid,
          ask: topOfBook.ask,
        }
      : { last: referencePrice, bid: null, ask: null };
  const limit = seedLimitPrice(prefs.limitPriceSource, side, book);
  const stop = seedStopPrice(side, referencePrice, prefs.stopOffsetPct);
  const orderType = prefs.orderType;
  const outsideRth = prefs.tradingHours === 'extended';
  return {
    orderType,
    quantityValue: defaultTicketQty(),
    limitPrice: formatSeedPrice(limit),
    stopPrice: formatSeedPrice(stop),
    outsideRth,
    side,
  };
}

export function seedPricesForSide(
  side: ManualOrderSide,
  orderType: ManualOrderType,
  symbolKey: string,
  referencePrice: number | null,
  topOfBook: TopOfBookLike | null,
): { limitPrice: string; stopPrice: string } {
  const prefs = readTradeDefaultsPrefs();
  const book =
    topOfBook && topOfBook.symbol.toUpperCase() === symbolKey.toUpperCase()
      ? {
          last: referencePrice,
          bid: topOfBook.bid,
          ask: topOfBook.ask,
        }
      : { last: referencePrice, bid: null, ask: null };
  return {
    limitPrice: usesLimitPrice(orderType)
      ? formatSeedPrice(seedLimitPrice(prefs.limitPriceSource, side, book))
      : '',
    stopPrice:
      orderType === 'TRAIL'
        ? formatSeedPrice(seedTrailAmount(referencePrice, prefs.stopOffsetPct))
        : usesStopPrice(orderType)
          ? formatSeedPrice(
              seedStopPrice(side, referencePrice, prefs.stopOffsetPct),
            )
          : '',
  };
}
