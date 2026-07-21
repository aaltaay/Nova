/**
 * Orders (Today) bucket filters — Working / Filled / Canceled / Partial / All.
 */
import type { ClosedOrdersFilter } from '../closed_orders/types';
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
