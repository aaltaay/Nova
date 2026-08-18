import type { ClosedOrder } from './types';

/** Session orderId 0 is not a real id -- show ledger/permId or --. */
export function formatClosedOrderId(order: Pick<ClosedOrder, 'order_id' | 'perm_id'>): string {
  const sessionId = Number(order.order_id);
  if (Number.isFinite(sessionId) && sessionId > 0) {
    return String(Math.trunc(sessionId));
  }
  const permId = Number(order.perm_id);
  if (Number.isFinite(permId) && permId > 0) {
    return String(Math.trunc(permId));
  }
  return '--';
}
