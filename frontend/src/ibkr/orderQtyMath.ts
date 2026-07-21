/**
 * Pure qty math for Open / Closed order rows and Fill now.
 *
 * Broker (IBKR) owns filled_qty, remaining_qty, avg_fill_price, limit/stop.
 * Nova only derives remaining when the broker field is missing, and clamps
 * negatives / fractional shares for market actions.
 */
import type { IbkrOrder } from './types';

export type OrderQtyFields = Pick<
  IbkrOrder,
  'qty' | 'filled_qty' | 'remaining_qty'
>;

/** Shares still working — prefer broker remaining; else qty − filled. */
export function remainingShares(order: OrderQtyFields): number {
  if (order.remaining_qty != null && Number.isFinite(order.remaining_qty)) {
    return Math.max(0, order.remaining_qty);
  }
  const filled = order.filled_qty ?? 0;
  const qty = Number.isFinite(order.qty) ? order.qty : 0;
  return Math.max(0, qty - filled);
}

/** Whole shares for Fill now / market place (IB equity path). */
export function remainingSharesWhole(order: OrderQtyFields): number {
  return Math.max(0, Math.floor(remainingShares(order)));
}

/** filled + remaining === qty when both broker fields are present. */
export function fillProgressCoherent(order: OrderQtyFields): boolean {
  if (order.remaining_qty == null || !Number.isFinite(order.remaining_qty)) {
    return true;
  }
  const filled = order.filled_qty ?? 0;
  const qty = Number.isFinite(order.qty) ? order.qty : 0;
  return Math.abs(filled + order.remaining_qty - qty) < 1e-6;
}

/**
 * Closed / terminal rows: either working coherence, or remaining cleared to 0
 * after cancel (partial cancel leaves filled less than qty with remaining 0).
 */
export function closedFillProgressAcceptable(order: OrderQtyFields): boolean {
  if (fillProgressCoherent(order)) return true;
  const rem = order.remaining_qty;
  if (rem == null || !Number.isFinite(rem) || rem !== 0) return false;
  const filled = order.filled_qty ?? 0;
  const qty = Number.isFinite(order.qty) ? order.qty : 0;
  return filled >= 0 && filled <= qty + 1e-6;
}
