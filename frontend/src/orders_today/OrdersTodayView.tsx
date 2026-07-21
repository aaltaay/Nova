/**
 * Orders (Today) body — segmented Working / Filled / Canceled / Partial / All.
 * Hosted by Stock View footer dock (Webull Orders → Today's Orders).
 */
import { useMemo, useState } from 'react';
import { ClosedOrdersPanel } from '../closed_orders/ClosedOrdersPanel';
import { buildMockClosedOrders } from '../closed_orders/mockClosedOrders';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { WorkingOrdersPanel } from '../ibkr/WorkingOrdersPanel';
import type { IbkrOrder } from '../ibkr/types';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import {
  closedFilterFromToday,
  filterWorkingForToday,
  showWorkingForToday,
} from './filterOrdersToday';
import { OrdersTodayFilters } from './OrdersTodayFilters';
import type { OrdersTodayFilter } from './types';

interface Props {
  symbol: string;
  workingOrders: IbkrOrder[];
  usingWorkingSample: boolean;
  onCancelOrder?: (id: number) => void;
  onFillImmediately?: (order: IbkrOrder) => void;
  highlightOrderId?: number | null;
  filter: OrdersTodayFilter;
  onFilterChange: (next: OrdersTodayFilter) => void;
}

export function OrdersTodayView({
  symbol,
  workingOrders,
  usingWorkingSample,
  onCancelOrder,
  onFillImmediately,
  highlightOrderId = null,
  filter,
  onFilterChange,
}: Props) {
  const status = useIbkrStatus();
  const { orders: closedLive } = useClosedOrders(status.connected);
  const [preferClosedSample, setPreferClosedSample] = useState(true);

  const usingClosedSample = closedLive.length === 0 && preferClosedSample;
  const closedSource = useMemo(
    () => (usingClosedSample ? buildMockClosedOrders(symbol) : closedLive),
    [usingClosedSample, closedLive, symbol],
  );

  const workingRows = useMemo(
    () => filterWorkingForToday(workingOrders, filter, symbol),
    [workingOrders, filter, symbol],
  );
  const closedStatusFilter = closedFilterFromToday(filter);
  const showWorking = showWorkingForToday(filter);
  const showClosed = closedStatusFilter != null;

  const empty =
    (!showWorking || workingRows.length === 0) &&
    (!showClosed || closedSource.length === 0);

  return (
    <div className="orders-today-view" data-testid="orders-today-view">
      <div className="orders-today-view__toolbar">
        <OrdersTodayFilters value={filter} onChange={onFilterChange} />
        {showClosed && closedLive.length === 0 && (
          <button
            type="button"
            className="orders-today-view__sample-btn"
            data-testid="orders-today-closed-sample-toggle"
            onClick={() => setPreferClosedSample((v) => !v)}
          >
            {preferClosedSample ? 'Hide closed sample' : 'Show closed sample'}
          </button>
        )}
      </div>

      {empty ? (
        <div className="ibkr-empty" data-testid="orders-today-empty">
          No orders in this filter for today.
        </div>
      ) : (
        <>
          {showWorking && workingRows.length > 0 && (
            <div data-testid="stock-view-working-orders">
              <WorkingOrdersPanel
                orders={workingRows}
                filterSymbol={symbol}
                hideTitle
                compact={false}
                onCancelOrder={usingWorkingSample ? undefined : onCancelOrder}
                onFillImmediately={
                  usingWorkingSample ? undefined : onFillImmediately
                }
                highlightOrderId={
                  usingWorkingSample ? 90001 : highlightOrderId
                }
              />
            </div>
          )}
          {showClosed && (
            <div data-testid="stock-view-closed-orders">
              <ClosedOrdersPanel
                orders={closedSource}
                filterSymbol={symbol}
                selectedSymbol={symbol}
                hideTitle
                hideFilters
                statusFilter={closedStatusFilter}
                sampleMode={usingClosedSample}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
