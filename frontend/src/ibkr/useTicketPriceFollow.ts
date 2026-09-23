/**
 * The ticket's limit follows a side of the live book. After Bid / Mid / Ask
 * (or a Settings seed read from the book) every Level 2 change moves the limit
 * with it, until the operator types a price, clicks the lit button again, or
 * changes symbol, side or order type -- the ticket owns those stops.
 *
 * The price holds while `frozen` (the confirm dialog is open or an order is in
 * flight), so the field never moves under a confirm. With no book for the
 * symbol it holds where it was; last trade is never substituted.
 */
import { useEffect, useState } from 'react';
import type { TopOfBookLike } from './applyTicketDefaults';
import { quickPriceFromBook, type QuickPriceKind } from './ticketPriceQuick';

interface Params {
  symbol: string;
  book: TopOfBookLike | null;
  /** The side a fresh ticket follows, from its Settings seed. */
  initial: QuickPriceKind | null;
  /** The limit field is on the ticket (LMT / STP LMT). */
  active: boolean;
  frozen: boolean;
  setLimitPrice: (price: string) => void;
}

export function useTicketPriceFollow({ symbol, book, initial, active, frozen, setLimitPrice }: Params) {
  const [following, setFollowing] = useState<QuickPriceKind | null>(initial);
  const price = following ? quickPriceFromBook(following, book, symbol) : null;

  useEffect(() => {
    if (active && !frozen && price != null) setLimitPrice(price);
  }, [price, active, frozen, setLimitPrice]);

  return { following, setFollowing };
}
