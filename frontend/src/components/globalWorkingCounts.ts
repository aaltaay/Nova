/** Pure Working-menu counters from open + closed session orders. */
import { filterClosedOrders } from '../closed_orders/filterClosedOrders';
import type { ClosedOrder } from '../closed_orders/types';
import type { IbkrOrder } from '../ibkr/types';

export interface GlobalWorkingCounts {
  working: number;
  filledToday: number;
  canceledFailed: number;
}

export function globalWorkingCounts(
  workingOrders: IbkrOrder[],
  closedOrders: ClosedOrder[],
): GlobalWorkingCounts {
  return {
    working: workingOrders.length,
    filledToday: filterClosedOrders(closedOrders, 'filled').length,
    canceledFailed: filterClosedOrders(closedOrders, 'cancelled').length,
  };
}

/** Unique symbols with at least one working order (for cancel-all). */
export function workingOrderSymbols(orders: IbkrOrder[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const o of orders) {
    const sym = (o.symbol || '').trim().toUpperCase();
    if (!sym || seen.has(sym)) continue;
    seen.add(sym);
    out.push(sym);
  }
  return out;
}
