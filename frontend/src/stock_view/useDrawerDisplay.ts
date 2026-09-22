/**
 * What the Trader drawer's Orders list shows and counts (QA V22). The sample
 * working orders stand in only while the account has none and the operator
 * has not hidden them; while they show, the list and every count are the
 * sample alone -- real closed rows used to be mixed in and counted with it
 * ("12 SAMPLE").
 */
import { useMemo } from 'react';
import type { ClosedOrder } from '../closed_orders/types';
import { ORDERS_TODAY_FILTERS, type OrdersTodayFilterId, type StockViewDockSurface } from '../constants';
import { buildMockWorkingOrders } from '../ibkr/mockWorkingOrders';
import type { IbkrOrder } from '../ibkr/types';
import { ordersTodayBadgeCount } from '../orders_today';
import type { OrdersTodayFilter } from '../orders_today';

const NO_CLOSED: ClosedOrder[] = [];

export interface DrawerDisplayInput {
  surface: StockViewDockSurface;
  filter: OrdersTodayFilter;
  orders: IbkrOrder[];
  closedOrders: ClosedOrder[];
  sampleHidden: boolean;
  symbolKey: string;
}

export interface DrawerDisplay {
  wantsWorkingSample: boolean;
  usingSample: boolean;
  displayOrders: IbkrOrder[];
  displayClosed: ClosedOrder[];
  openCount: number;
  filterCounts: Partial<Record<OrdersTodayFilterId, number>>;
}

export function useDrawerDisplay({
  surface, filter, orders, closedOrders, sampleHidden, symbolKey,
}: DrawerDisplayInput): DrawerDisplay {
  const wantsWorkingSample =
    surface === 'orders' &&
    (filter === 'working' || filter === 'all' || filter === 'partial_filled');
  // Account-wide desk: sample only when the account has zero working orders.
  const usingSample = wantsWorkingSample && orders.length === 0 && !sampleHidden;
  const displayOrders = useMemo(
    () => (usingSample ? buildMockWorkingOrders(symbolKey) : orders),
    [usingSample, symbolKey, orders],
  );
  const displayClosed = usingSample ? NO_CLOSED : closedOrders;
  const openCount = ordersTodayBadgeCount(displayOrders, displayClosed, filter, null);
  // One count per status chip, the same rule as the badge.
  const filterCounts = useMemo(() => {
    const out: Partial<Record<OrdersTodayFilterId, number>> = {};
    for (const f of ORDERS_TODAY_FILTERS) {
      out[f.id] = ordersTodayBadgeCount(displayOrders, displayClosed, f.id, null);
    }
    return out;
  }, [displayOrders, displayClosed]);
  return { wantsWorkingSample, usingSample, displayOrders, displayClosed, openCount, filterCounts };
}
