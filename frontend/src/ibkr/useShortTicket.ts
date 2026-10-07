/**
 * The ticket's short side, in one place (ADR 048, #778 step 3), so the ticket only wires it.
 *
 * - The sides follow the position (`shortTicketModel.sideButtons`): flat Buy / Short, long Buy / Sell with
 *   Short off, short Cover / Short more with Sell off.
 * - A short is a Limit with a required Buy stop. Choosing Short prices the limit at the ask while SSR is on
 *   or not known -- a short under SSR may execute only above the bid -- else at the bid, and starts the stop
 *   the venue's Settings > Trade offset over it.
 * - While Short is chosen the short check is asked with the ticket's numbers (`useShortCheck`), so the SHORT
 *   CHECK box lists every rule the door will run, with its numbers, before the operator presses.
 */
import { useEffect, useMemo, useState } from 'react';
import type { TopOfBookLike } from './applyTicketDefaults';
import type { QuantityMode } from './orderEntry';
import { marginNumbers, SHORT_CHECK_TICKET_POLL_MS, useShortCheck, type ShortCheckState } from './shortCheck';
import { useShortFacts } from './shortFacts';
import {
  buyStopRefusal,
  heldSide,
  openSide,
  seedBuyStop,
  shortLimitNote,
  shortLimitSide,
  shortSubmitLabel,
  sideButtons,
  sideNote,
  type SideButton,
} from './shortTicketModel';
import type { TicketSide } from './ticketSide';
import type { IbkrAccountSummary, IbkrPosition } from './types';

interface Args {
  symbol: string;
  summary: IbkrAccountSummary | null;
  position: IbkrPosition | null;
  allowShort: boolean;
  shortBlock: string | null;
  ticketSide: TicketSide;
  orderType: string;
  quantityMode: QuantityMode;
  quantityValue: string;
  limitPrice: string;
  topOfBook: TopOfBookLike | null;
  /** The venue's Settings > Trade short buy stop offset, in dollars. */
  stopOffset: number;
}

export interface ShortTicket {
  buttons: SideButton[];
  note: string | null;
  /** The submit button's words for a short or a cover; null keeps the ticket's own. */
  submitLabel: string | null;
  /** A cover wears green, a short orange. */
  submitTone: 'short' | 'cover' | null;
  buyStop: string;
  setBuyStop: (next: string) => void;
  /** Why the short cannot be sent as typed (its buy stop); null when it can, or the side is not Short. */
  stopRefusal: string | null;
  check: ShortCheckState;
  /** Under the limit while Short is chosen: why it sits at the ask (SSR), or null. */
  limitNote: string | null;
  /** The short's margin requirement from the check (null until it answers, or for any other side). */
  margin: number | null;
  /** Where Short starts: the limit and the book side it follows, and the stop over it. */
  seed: () => { limit: string | null; follow: 'ask' | 'bid'; stop: string };
  /** The buy stop a short at ``limit`` starts with (the venue's offset over it). */
  stopFor: (limit: string) => string;
}

function bookPrice(book: TopOfBookLike | null, symbol: string, side: 'ask' | 'bid'): number | null {
  if (!book || book.symbol.trim().toUpperCase() !== symbol.trim().toUpperCase()) return null;
  const px = side === 'ask' ? book.ask : book.bid;
  return px != null && px > 0 ? px : null;
}

export function useShortTicket(a: Args): ShortTicket {
  const [buyStop, setBuyStop] = useState('');
  const qty = a.position?.qty ?? null;
  const known = a.summary != null;
  const orderQty = a.quantityMode === 'shares' ? a.quantityValue : '';
  const shortLock = a.allowShort ? a.shortBlock : null;
  const buttons = useMemo(
    () => sideButtons({ symbol: a.symbol, qty, known, allowShort: a.allowShort, shortBlock: shortLock }),
    [a.symbol, qty, known, a.allowShort, shortLock],
  );
  const shortChosen = a.ticketSide === 'short';
  const shortAvailable = openSide(buttons, 'short') != null;
  const shortOpen = shortChosen && shortAvailable;
  // SSR is read while Short can be pressed, so the press prices the limit right (the ask under SSR).
  const facts = useShortFacts(a.symbol, shortAvailable);
  const shares = Number(orderQty);
  const params = shortOpen && Number.isFinite(shares) && shares > 0
    ? { qty: shares, price: Number(a.limitPrice) || null, stop: Number(buyStop) || null }
    : null;
  const check = useShortCheck(a.symbol, params, SHORT_CHECK_TICKET_POLL_MS);

  useEffect(() => setBuyStop(''), [a.symbol]);

  const ssrEffective = (check.check ?? facts.check)?.ssr?.effective_on ?? null;
  const label = shortSubmitLabel({
    ticketSide: a.ticketSide, qty, symbol: a.symbol, orderQty, limit: a.limitPrice, buyStop, orderType: a.orderType,
  });
  const held = heldSide(qty);
  return {
    buttons,
    note: sideNote(a.ticketSide, qty, orderQty, a.symbol),
    submitLabel: label,
    submitTone: shortChosen ? 'short' : a.ticketSide === 'buy' && held === 'short' ? 'cover' : null,
    buyStop,
    setBuyStop,
    stopRefusal: shortChosen ? buyStopRefusal(a.limitPrice, buyStop) : null,
    check,
    limitNote: shortChosen ? shortLimitNote(ssrEffective) : null,
    margin: shortChosen ? marginNumbers(check.check).requirement : null,
    seed: () => {
      const follow = shortLimitSide(ssrEffective);
      const price = bookPrice(a.topOfBook, a.symbol, follow);
      const limit = price != null ? price.toFixed(2) : null;
      return { limit, follow, stop: seedBuyStop(limit ?? a.limitPrice, a.stopOffset) };
    },
    stopFor: (limit: string) => seedBuyStop(limit, a.stopOffset),
  };
}
