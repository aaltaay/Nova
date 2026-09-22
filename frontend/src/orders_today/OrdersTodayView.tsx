/**
 * Orders (Today) body — segmented Working / Filled / Canceled / Partial / All.
 * Hosted by Stock View footer dock (Webull Orders → Today's Orders).
 */
import { useMemo, useState } from 'react';
import { ClosedOrdersPanel } from '../closed_orders/ClosedOrdersPanel';
import { buildMockClosedOrders } from '../closed_orders/mockClosedOrders';
import type { ClosedOrder } from '../closed_orders/types';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import {
  ORDERS_TODAY_EMPTY_FILTER_MESSAGE,
  ORDERS_TODAY_EMPTY_MESSAGE,
} from '../constants';
import { WorkingOrdersPanel } from '../ibkr/WorkingOrdersPanel';
import type { IbkrOrder } from '../ibkr/types';
import {
  closedFilterFromToday,
  closedRowsForToday,
  filterWorkingForToday,
  showWorkingForToday,
} from './filterOrdersToday';
import { OrdersTodayFilters } from './OrdersTodayFilters';
import type { OrdersTodayFilter } from './types';

interface Props {
  symbol: string;
  workingOrders: IbkrOrder[];
  usingWorkingSample: boolean;
  /** Live (real, never sample) closed orders — pre-fetched by the parent
   * dock so the badge count and this panel poll the same list once. */
  closedOrders: ClosedOrder[];
  onCancelOrder?: (id: number) => void;
  onFillImmediately?: (order: IbkrOrder) => void;
  highlightOrderId?: number | null;
  filter: OrdersTodayFilter;
  onFilterChange: (next: OrdersTodayFilter) => void;
  /** The Trader drawer hosts the status chips on its own tab row. */
  hideFilters?: boolean;
}

export function OrdersTodayView({
  symbol,
  workingOrders,
  usingWorkingSample,
  closedOrders,
  onCancelOrder,
  onFillImmediately,
  highlightOrderId = null,
  filter,
  onFilterChange,
  hideFilters = false,
}: Props) {
  const sample = useSampleDataOptional();
  const [preferClosedSample, setPreferClosedSample] = useState(() => Boolean(sample));

  const usingClosedSample = closedOrders.length === 0 && preferClosedSample;
  // The sample desk's closed sample sits at the sample symbol's own price (QA W31).
  const anchor = sample && symbol ? sample.tickerDetail(symbol).snapshot.latest_trade?.price ?? null : null;
  const closedSource = useMemo(
    () => (usingClosedSample ? buildMockClosedOrders(symbol, anchor) : closedOrders),
    [usingClosedSample, closedOrders, symbol, anchor],
  );

  // Account-wide: do not scope Orders (Today) to the open Stock View ticker.
  const workingRows = useMemo(
    () => filterWorkingForToday(workingOrders, filter, null),
    [workingOrders, filter],
  );
  const closedRows = useMemo(
    () => closedRowsForToday(closedSource, filter, null),
    [closedSource, filter],
  );
  const closedStatusFilter = closedFilterFromToday(filter);
  const showWorking = showWorkingForToday(filter);
  const showClosed = closedStatusFilter != null;

  const empty =
    (!showWorking || workingRows.length === 0) &&
    (!showClosed || closedRows.length === 0);
  // Gateway truly has nothing yet vs this filter segment has no matches.
  const hasAnyRealData = workingOrders.length > 0 || closedOrders.length > 0;
  const emptyMessage = hasAnyRealData
    ? ORDERS_TODAY_EMPTY_FILTER_MESSAGE
    : ORDERS_TODAY_EMPTY_MESSAGE;

  const closedSampleToggle = showClosed && closedOrders.length === 0;

  return (
    <div className="orders-today-view" data-testid="orders-today-view">
      {(!hideFilters || closedSampleToggle) && (
        <div className="orders-today-view__toolbar">
          {!hideFilters && <OrdersTodayFilters value={filter} onChange={onFilterChange} />}
          {closedSampleToggle && (
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
      )}

      {empty ? (
        <div className="ibkr-empty" data-testid="orders-today-empty">
          {emptyMessage}
        </div>
      ) : (
        <>
          {showWorking && workingRows.length > 0 && (
            <div data-testid="stock-view-working-orders">
              <WorkingOrdersPanel
                orders={workingRows}
                filterSymbol={null}
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
                filterSymbol={null}
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
