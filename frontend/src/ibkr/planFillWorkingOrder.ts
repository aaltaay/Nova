/**
 * Decide what Fill now can honestly send.
 *
 * IBKR does not fill MKT outside regular hours (Warning 2109 ignores
 * outsideRth on market orders; Warning 399 holds until the open). The
 * ticket may send MKT+EH from the Extended Hours checkbox (#170); that
 * does not make those MKTs fill. Fill now used to cancel+resubmit the
 * same unfillable MKT and treat broker-accept as success (#168).
 */
import type { MarketSessionKind } from '../chart/sessionHighlight';
import { FILL_WORKING_ORDER_CONFIRM_PREFIX } from '../constants';
import { formatMoney } from '../utils/formatMoney';
import { resolveFillSessionKind } from './extendedSession';
import { remainingSharesWhole } from './orderQtyMath';
import type { IbkrOrder } from './types';

export type FillWorkingBook = {
  symbol: string;
  bid: number | null;
  ask: number | null;
};

export type FillWorkingPlanOk = {
  ok: true;
  qty: number;
  side: 'BUY' | 'SELL';
  symbol: string;
  order_type: 'MKT' | 'LMT';
  limit_price?: number;
  outside_rth: boolean;
  confirmMessage: string;
};

export type FillWorkingPlan = FillWorkingPlanOk | { ok: false; error: string };

export type PlanFillWorkingOrderOptions = {
  book?: FillWorkingBook | null;
  sessionKind?: MarketSessionKind;
  now?: Date;
};

export { resolveFillSessionKind } from './extendedSession';

function sessionPhrase(kind: MarketSessionKind): string {
  if (kind === 'premarket') return 'premarket';
  if (kind === 'afterhours') return 'after-hours';
  if (kind === 'closed') return 'overnight';
  return 'regular hours';
}

function oppositeQuote(
  side: 'BUY' | 'SELL',
  book: FillWorkingBook | null,
): number | null {
  if (!book) return null;
  const px = side === 'SELL' ? book.bid : book.ask;
  return px != null && Number.isFinite(px) && px > 0 ? px : null;
}

export function bookForOrderSymbol(
  book: FillWorkingBook | null | undefined,
  symbol: string,
): FillWorkingBook | null {
  if (!book) return null;
  if (book.symbol.trim().toUpperCase() !== symbol) return null;
  return book;
}

function noSweepError(args: {
  symbol: string;
  side: 'BUY' | 'SELL';
  sessionKind: MarketSessionKind;
  book: FillWorkingBook | null | undefined;
  alreadyMarket: boolean;
}): string {
  const quoteName = args.side === 'SELL' ? 'bid' : 'ask';
  const when = sessionPhrase(args.sessionKind);
  const desk =
    args.book && args.book.symbol.trim().toUpperCase() !== args.symbol
      ? ` (desk book is on ${args.book.symbol.trim().toUpperCase()})`
      : '';
  if (args.alreadyMarket) {
    return (
      `IBKR does not fill market orders in ${when}. Fill now will not cancel ` +
      `and resubmit the same unfillable MKT on ${args.symbol}. Open ${args.symbol} ` +
      `in Trader for a live ${quoteName}, then Fill now can sweep a limit -- ` +
      `or wait for 9:30 ET.`
    );
  }
  return (
    `Fill now cannot sweep ${args.symbol} -- no live ${quoteName}${desk}. ` +
    `IBKR does not fill market orders in ${when}. Open ${args.symbol} in ` +
    `Trader or wait for 9:30 ET. The resting order was not cancelled.`
  );
}

function mktConfirmMessage(side: 'BUY' | 'SELL', qty: number, symbol: string): string {
  return `${FILL_WORKING_ORDER_CONFIRM_PREFIX}: ${side} ${qty} ${symbol}?`;
}

function lmtConfirmMessage(
  side: 'BUY' | 'SELL',
  qty: number,
  symbol: string,
  limitPrice: number,
): string {
  const quoteName = side === 'SELL' ? 'bid' : 'ask';
  return (
    `Fill now will cancel the resting order and sweep ${side} ${qty} ${symbol} ` +
    `at ${quoteName} ${formatMoney(limitPrice)} (extended-hours limit). ` +
    `No US exchange takes a market order outside regular hours.`
  );
}

/** Plan first -- never cancel until this says a real fill path exists. */
export function planFillWorkingOrder(
  order: IbkrOrder,
  options?: PlanFillWorkingOrderOptions,
): FillWorkingPlan {
  const qty = remainingSharesWhole(order);
  if (qty <= 0) {
    return { ok: false, error: 'Nothing left to fill on this order' };
  }
  const side = order.side === 'SELL' ? 'SELL' : 'BUY';
  const symbol = order.symbol.trim().toUpperCase();
  const sessionKind = resolveFillSessionKind(options);
  const matched = bookForOrderSymbol(options?.book, symbol);
  const sweepPx = oppositeQuote(side, matched);

  if (sessionKind === 'rth') {
    return {
      ok: true,
      qty,
      side,
      symbol,
      order_type: 'MKT',
      outside_rth: Boolean(order.outside_rth),
      confirmMessage: mktConfirmMessage(side, qty, symbol),
    };
  }

  if (sweepPx != null) {
    return {
      ok: true,
      qty,
      side,
      symbol,
      order_type: 'LMT',
      limit_price: sweepPx,
      outside_rth: true,
      confirmMessage: lmtConfirmMessage(side, qty, symbol, sweepPx),
    };
  }

  return {
    ok: false,
    error: noSweepError({
      symbol,
      side,
      sessionKind,
      book: options?.book,
      alreadyMarket: order.order_type === 'MKT',
    }),
  };
}
