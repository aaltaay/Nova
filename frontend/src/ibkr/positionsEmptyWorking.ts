/**
 * "No open positions" is never the whole story while an order works (ADR 045 amendment 2026-10-14).
 *
 * GENK, 2026-10-14: a Paper buy of 1,000 at 2.76 worked for three minutes while the Positions tab said only
 * "No open positions." -- the operator read it as nothing going on ("It seems like there was a hidden working
 * order or a hidden position"), and the order filled and the bot trip sold it within a second. The empty state
 * now names every working order: side, size, symbol, price and since when.
 */
import { formatShareQty } from '../utils/formatShareQty';
import { fmtTapeTime } from './TapeRow';
import type { IbkrOrder } from './types';

function priceWords(order: IbkrOrder): string {
  const type = (order.order_type || '').toUpperCase();
  if (type === 'MKT') return 'at market';
  const price = type.startsWith('STP') ? order.stop_price : order.limit_price;
  return typeof price === 'number' && Number.isFinite(price) ? `${type} ${price}` : type;
}

/** "Buy 1,000 GENK LMT 2.76 since 09:25:19 ET" for one working order. */
export function workingOrderWords(order: IbkrOrder): string {
  const side = order.side === 'SELL' ? 'Sell' : 'Buy';
  const left = order.remaining_qty ?? order.qty;
  const qty = typeof left === 'number' && Number.isFinite(left) ? `${formatShareQty(left)} ` : '';
  const since = order.submitted_at ? ` since ${fmtTapeTime(order.submitted_at)} ET` : '';
  return `${side} ${qty}${order.symbol} ${priceWords(order)}${since}`;
}

/** The line under "No open positions." while orders work, else null. */
export function positionsEmptyWorkingLine(orders: readonly IbkrOrder[]): string | null {
  if (!orders.length) return null;
  const head = orders.length === 1 ? '1 working order' : `${orders.length} working orders`;
  return `${head}: ${orders.map(workingOrderWords).join('; ')}. Each becomes a position the moment it fills.`;
}
