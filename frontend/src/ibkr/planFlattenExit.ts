/**
 * Flatten / close / KILL exit ticket -- mirror of backend execution/flatten_exit.py.
 *
 * Weekday RTH: MKT outside_rth=false.
 * Otherwise: EH LMT at bid (SELL) / ask (BUY) / last. Never RTH-only MKT
 * (IBKR Warning 2109 / 399 held_until next regular session).
 */
import type { MarketSessionKind } from '../chart/sessionHighlight';
import { FLATTEN_EH_NO_MARK } from '../constants';
import {
  flattenNeedsOutsideRth,
  resolveFillSessionKind,
} from './extendedSession';

export type FlattenExitBook = {
  bid?: number | null;
  ask?: number | null;
  last?: number | null;
};

export type FlattenExitTicket =
  | {
      ok: true;
      order_type: 'MKT' | 'LMT';
      outside_rth: boolean;
      limit_price?: number;
      quote_source?: 'bid' | 'ask' | 'last';
    }
  | { ok: false; error: string };

function positive(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  return value;
}

export function flattenSweepLimit(
  side: 'BUY' | 'SELL',
  book?: FlattenExitBook | null,
): { limit_price: number; quote_source: 'bid' | 'ask' | 'last' } | null {
  const opposite = side === 'SELL' ? positive(book?.bid) : positive(book?.ask);
  if (opposite != null) {
    return { limit_price: opposite, quote_source: side === 'SELL' ? 'bid' : 'ask' };
  }
  const last = positive(book?.last);
  if (last != null) return { limit_price: last, quote_source: 'last' };
  return null;
}

export function planFlattenExit(
  side: 'BUY' | 'SELL',
  options?: {
    now?: Date;
    sessionKind?: MarketSessionKind;
    book?: FlattenExitBook | null;
    forceExtended?: boolean;
    outsideRth?: boolean | null;
  },
): FlattenExitTicket {
  const forced =
    options?.forceExtended
    || options?.outsideRth === true
    || (options?.outsideRth !== false
      && flattenNeedsOutsideRth(options?.now, options?.sessionKind));
  if (!forced) {
    return { ok: true, order_type: 'MKT', outside_rth: false };
  }
  const sweep = flattenSweepLimit(side, options?.book);
  if (!sweep) {
    return { ok: false, error: FLATTEN_EH_NO_MARK };
  }
  return {
    ok: true,
    order_type: 'LMT',
    outside_rth: true,
    limit_price: sweep.limit_price,
    quote_source: sweep.quote_source,
  };
}

/** Session kind that treats weekend clock-RTH as closed (Fill now + flatten). */
export function flattenSessionKind(
  options?: { now?: Date; sessionKind?: MarketSessionKind },
): MarketSessionKind {
  return resolveFillSessionKind(options);
}
