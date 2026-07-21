import { formatOrderStatus } from '../ibkr/orderDisplay';
import type { ClosedOrder, ClosedOrdersFilter } from './types';

/** Pure filter for Closed Orders tabs (all / filled / cancelled / partial). */
export function filterClosedOrders(
  orders: ClosedOrder[],
  filter: ClosedOrdersFilter,
  symbol?: string | null,
): ClosedOrder[] {
  const key = symbol?.trim().toUpperCase() || null;
  return orders.filter((o) => {
    if (key && o.symbol.toUpperCase() !== key) return false;
    if (filter === 'all') return true;
    const label = formatOrderStatus(o.status, o.filled_qty ?? 0, o.qty);
    if (filter === 'filled') return label === 'Filled';
    if (filter === 'cancelled') {
      // Zero-fill cancel / failed — partial cancels use the Partial tab.
      return label === 'Cancelled' || label === 'Failed';
    }
    if (filter === 'partial') return label === 'Cancelled (partial fill)';
    return true;
  });
}
