/**
 * The ticket's sides in motion (ADR 048, #778 step 3), off the ticket component.
 *
 * - Choosing a side seeds its prices. A Short is a Limit: at the ask while SSR is on or not known (a short under
 *   SSR may execute only above the bid), else at the bid, with its Buy stop the venue's Settings > Trade offset
 *   over the limit.
 * - A staged order (the chart menu, the plan's "Stage short in ticket") lands on its own side. A side the position
 *   locks refuses it with the lock's words: a staged sale never becomes a buy.
 * - A side the position locks while it is pressed gives way (`sideAfterLock`: Short to Sell when you went long,
 *   anything else to Buy, which is Cover while short), its prices seeded again, any open confirm dropped.
 * - A short is always a Limit: a defaults change to Market never reaches it.
 */
import { useEffect, useRef } from 'react';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { seedFollow, seedPricesForSide, type TopOfBookLike } from './applyTicketDefaults';
import { usesLimitPrice, usesStopPrice, type ManualOrderType, type QuantityMode } from './orderEntry';
import { subscribeOrderTicketPrefill } from './orderTicketPrefill';
import { openSide, sideAfterLock } from './shortTicketModel';
import type { QuickPriceKind } from './ticketPriceQuick';
import { orderSideToTicketSide, ticketSideToOrder, type TicketSide } from './ticketSide';
import type { ShortTicket } from './useShortTicket';

interface Args {
  venue: DeskVenue | null;
  symbol: string;
  ticketSide: TicketSide;
  orderType: ManualOrderType;
  referencePrice: number | null;
  topOfBook: TopOfBookLike | null;
  /** The quantity is the safety gate's (forced): a staged size never replaces it. */
  quantityLocked: boolean;
  short: ShortTicket;
  setTicketSide: (side: TicketSide) => void;
  setOrderType: (orderType: ManualOrderType) => void;
  setQuantityMode: (mode: QuantityMode) => void;
  setQuantityValue: (value: string) => void;
  setLimitPrice: (value: string) => void;
  setStopPrice: (value: string) => void;
  setFollowing: (kind: QuickPriceKind | null) => void;
  resetSubmission: () => void;
  /** Drop an open confirm, keeping the Last line (the side moved under it: what it names is no longer this side). */
  cancelConfirm: () => void;
  /** Put a refusal on the ticket's Last line (a staged order whose side is locked). */
  say: (result: { ok: boolean; text: string }) => void;
}

export function useTicketSideActions(a: Args): (next: TicketSide) => void {
  const latest = useRef(a);
  latest.current = a;

  /** Move to ``next`` and seed its prices. ``pressed``: the operator chose it (a fresh ticket); else a lock moved it. */
  function move(next: TicketSide, pressed: boolean): void {
    const p = latest.current;
    p.setTicketSide(next);
    if (next === 'short') {
      const seed = p.short.seed();
      p.setOrderType('LMT');
      if (seed.limit != null) p.setLimitPrice(seed.limit);
      p.setFollowing(seed.limit != null ? seed.follow : null);
      p.short.setBuyStop(seed.stop);
    } else {
      const mapped = ticketSideToOrder(next);
      const seeded = seedPricesForSide(p.venue, mapped.side, p.orderType, p.symbol, p.referencePrice, p.topOfBook);
      if (usesLimitPrice(p.orderType)) p.setLimitPrice(seeded.limitPrice);
      p.setFollowing(seedFollow(p.venue, mapped.side, p.orderType));
      if (usesStopPrice(p.orderType)) p.setStopPrice(seeded.stopPrice);
    }
    // A lock moved it after a fill: the Last line keeps that fill's words.
    if (pressed) p.resetSubmission();
    else p.cancelConfirm();
  }

  function select(next: TicketSide): void {
    if (!openSide(latest.current.short.buttons, next)) return;
    move(next, true);
  }

  // A staged order: the PIN / spend / confirm gates still own the place.
  useEffect(() => {
    return subscribeOrderTicketPrefill(a.symbol, (req) => {
      const p = latest.current;
      const side: TicketSide = req.shortEntry ? 'short' : orderSideToTicketSide(req.side);
      const button = p.short.buttons.find((b) => b.side === side);
      if (!button || button.lock) {
        p.say({ ok: false, text: button?.lock ?? `${side} is not open on this account.` });
        return;
      }
      p.setTicketSide(side);
      p.setOrderType(req.orderType);
      p.setQuantityMode('shares');
      if (!p.quantityLocked) p.setQuantityValue(req.quantityValue);
      p.setLimitPrice(req.limitPrice);
      p.setFollowing(null);
      if (side === 'short') {
        p.short.setBuyStop(req.buyStop ?? p.short.stopFor(req.limitPrice));
      }
      p.resetSubmission();
    });
  }, [a.symbol]);

  // The position moved under the pressed side and locked it: give way, with that side's prices.
  const after = sideAfterLock(a.ticketSide, a.short.buttons);
  useEffect(() => {
    if (after !== latest.current.ticketSide) move(after, false);
  }, [after]);

  // A short is a Limit: a Settings change to Market (or Stop) never turns it into an unpriced short.
  useEffect(() => {
    if (a.ticketSide === 'short' && a.orderType !== 'LMT') latest.current.setOrderType('LMT');
  }, [a.ticketSide, a.orderType]);

  return select;
}
