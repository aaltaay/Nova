/** Reseed on venue/symbol changes; update only changed preferences in an edited ticket. */
import { useEffect, useRef } from 'react';
import type { DeskVenue } from '../constantGroups/desk_venue';
import type { TradeDefaultsPrefs } from '../settings';
import { applyTicketDefaults, seedFollow, seedPricesForSide, type TopOfBookLike } from './applyTicketDefaults';
import type { ManualOrderSide, ManualOrderType, QuantityMode } from './orderEntry';
import type { QuickPriceKind } from './ticketPriceQuick';
import { orderSideToTicketSide, type TicketSide } from './ticketSide';

interface Params {
  symbol: string;
  venue: DeskVenue | null;
  generation: string | null;
  prefs: TradeDefaultsPrefs;
  side: ManualOrderSide;
  orderType: ManualOrderType;
  referencePrice: number | null;
  topOfBook: TopOfBookLike | null;
  setTicketSide: (side: TicketSide) => void;
  setOrderType: (value: ManualOrderType) => void;
  setQuantityMode: (value: QuantityMode) => void;
  setQuantityValue: (value: string) => void;
  setLimitPrice: (value: string) => void;
  setStopPrice: (value: string) => void;
  setOutsideRth: (value: boolean) => void;
  setFollowing: (value: QuickPriceKind | null) => void;
  resetSubmission: () => void;
}

export function useTicketDefaultsSync(p: Params): void {
  const previous = useRef<Pick<Params, 'symbol' | 'venue' | 'generation' | 'prefs'> | null>(null);
  useEffect(() => {
    const old = previous.current;
    previous.current = { symbol: p.symbol, venue: p.venue, generation: p.generation, prefs: p.prefs };
    const fresh = !old || old.symbol !== p.symbol || old.venue !== p.venue || old.generation !== p.generation;
    if (fresh) {
      const next = applyTicketDefaults(p.venue, p.symbol, p.referencePrice, p.topOfBook);
      p.setTicketSide(orderSideToTicketSide(next.side));
      p.setOrderType(next.orderType);
      p.setQuantityMode('shares');
      p.setQuantityValue(next.quantityValue);
      p.setLimitPrice(next.limitPrice);
      p.setStopPrice(next.stopPrice);
      p.setOutsideRth(next.outsideRth);
      p.setFollowing(seedFollow(p.venue, next.side, next.orderType));
      p.resetSubmission();
      return;
    }
    if (old.prefs === p.prefs) return;
    const orderChanged = old.prefs.orderType !== p.prefs.orderType;
    const limitChanged = old.prefs.limitPriceSource !== p.prefs.limitPriceSource;
    const stopChanged = old.prefs.stopOffsetPct !== p.prefs.stopOffsetPct;
    if (orderChanged) p.setOrderType(p.prefs.orderType);
    if (orderChanged || limitChanged || stopChanged) {
      const type = orderChanged ? p.prefs.orderType : p.orderType;
      const prices = seedPricesForSide(p.venue, p.side, type, p.symbol, p.referencePrice, p.topOfBook);
      if (orderChanged || limitChanged) {
        p.setLimitPrice(prices.limitPrice);
        p.setFollowing(seedFollow(p.venue, p.side, type));
      }
      if (orderChanged || stopChanged) p.setStopPrice(prices.stopPrice);
    }
    if (old.prefs.quantity !== p.prefs.quantity) {
      p.setQuantityMode('shares');
      p.setQuantityValue(applyTicketDefaults(p.venue, p.symbol, p.referencePrice, p.topOfBook).quantityValue);
    }
    if (old.prefs.tradingHours !== p.prefs.tradingHours) p.setOutsideRth(p.prefs.tradingHours === 'extended');
    // TIF/legs update their own consumers; no preference edit overwrites unrelated prices.
    if (orderChanged || limitChanged || stopChanged || old.prefs.quantity !== p.prefs.quantity ||
      old.prefs.tradingHours !== p.prefs.tradingHours) p.resetSubmission();
  }, [p]);
}
