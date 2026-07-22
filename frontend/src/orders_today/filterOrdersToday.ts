/**
 * Orders (Today) bucket filters — Working / Filled / Canceled / Partial / All.
 */
import { filterClosedOrders } from '../closed_orders/filterClosedOrders';
import type { ClosedOrder, ClosedOrdersFilter } from '../closed_orders/types';
import { formatOrderStatus } from '../ibkr/orderDisplay';
import type { IbkrOrder } from '../ibkr/types';
import type { OrdersTodayFilter } from './types';

function statusLabel(o: IbkrOrder): string {
  return formatOrderStatus(o.status, o.filled_qty ?? 0, o.qty);
}

function isTerminalLabel(label: string): boolean {
  return (
    label === 'Filled' ||
    label === 'Cancelled' ||
    label === 'Cancelled (partial fill)' ||
    label === 'Failed'
  );
}

/** Working-side rows for the selected Orders (Today) segment. */
export function filterWorkingForToday(
  orders: IbkrOrder[],
  filter: OrdersTodayFilter,
  symbol?: string | null,
): IbkrOrder[] {
  if (filter === 'filled' || filter === 'canceled') return [];
  const key = symbol?.trim().toUpperCase() || null;
  return orders.filter((o) => {
    if (key && o.symbol.toUpperCase() !== key) return false;
    const label = statusLabel(o);
    if (isTerminalLabel(label)) return false;
    if (filter === 'partial_filled') return label === 'Partially filled';
    return true; // working | all
  });
}

/** Map Orders (Today) → ClosedOrdersPanel status filter; null = hide closed table. */
export function closedFilterFromToday(
  filter: OrdersTodayFilter,
): ClosedOrdersFilter | null {
  switch (filter) {
    case 'working':
      return null;
    case 'filled':
      return 'filled';
    case 'canceled':
      return 'cancelled';
    case 'partial_filled':
      return 'partial';
    case 'all':
      return 'all';
    default:
      return 'all';
  }
}

export function showWorkingForToday(filter: OrdersTodayFilter): boolean {
  return (
    filter === 'working' || filter === 'all' || filter === 'partial_filled'
  );
}

/**
 * Closed-side rows for the selected Orders (Today) segment — the single
 * source of truth for both the empty-state gate and the rendered
 * `ClosedOrdersPanel`, so they can never disagree (double empty-state).
 */
export function closedRowsForToday(
  orders: ClosedOrder[],
  filter: OrdersTodayFilter,
  symbol?: string | null,
): ClosedOrder[] {
  const closedStatusFilter = closedFilterFromToday(filter);
  if (!closedStatusFilter) return [];
  return filterClosedOrders(orders, closedStatusFilter, symbol);
}

/**
 * Orders tab badge = symbol-scoped working + *real* closed for the active
 * filter. Never counts closed sample rows (caller must pass live closed only).
 */
export function ordersTodayBadgeCount(
  workingOrders: IbkrOrder[],
  closedOrders: ClosedOrder[],
  filter: OrdersTodayFilter,
  symbol?: string | null,
): number {
  const working = showWorkingForToday(filter)
    ? filterWorkingForToday(workingOrders, filter, symbol).length
    : 0;
  return working + closedRowsForToday(closedOrders, filter, symbol).length;
}
