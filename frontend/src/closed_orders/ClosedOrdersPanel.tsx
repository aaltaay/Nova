/**
 * Closed Orders — Webull History / filled+cancelled lifecycle (WID-027).
 * Column order drag-persisted (shared localStorage with Working Orders).
 */
import { useMemo, useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import {
  CLOSED_ORDERS_EMPTY_MESSAGE,
  CLOSED_ORDERS_PANEL_TITLE,
  CLOSED_ORDERS_SAMPLE_BANNER,
} from '../constants';
import {
  OrderTableColumnHeader,
  OrderTableDnd,
} from '../ibkr/OrderTableColumnHeader';
import {
  formatOrderSide,
  formatOrderStatus,
  orderActivityIso,
  orderSideClass,
  orderSideRowClass,
  orderStatusTone,
} from '../ibkr/orderDisplay';
import {
  CLOSED_COLUMN_META,
  DEFAULT_CLOSED_ORDER_COLUMNS,
  normalizeColumnOrder,
  type ClosedOrderColumnId,
} from '../ibkr/orderTableColumns';
import { useOrderTableColumnOrder } from '../ibkr/useOrderTableColumnOrder';
import { renderClosedOrderCell } from './closedOrderCells';
import { filterClosedOrders } from './filterClosedOrders';
import type { ClosedOrder, ClosedOrdersFilter } from './types';

interface Props {
  orders: ClosedOrder[];
  selectedSymbol?: string | null;
  onSelectSymbol?: (symbol: string) => void;
  onOpenTrading?: (symbol: string) => void;
  filterSymbol?: string | null;
  hideTitle?: boolean;
  sampleMode?: boolean;
}

const FILTERS: { id: ClosedOrdersFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'filled', label: 'Filled' },
  { id: 'partial', label: 'Partial cancel' },
  { id: 'cancelled', label: 'Cancelled' },
];

export function ClosedOrdersPanel({
  orders,
  selectedSymbol = null,
  onSelectSymbol,
  onOpenTrading,
  filterSymbol = null,
  hideTitle = false,
  sampleMode = false,
}: Props) {
  const [filter, setFilter] = useState<ClosedOrdersFilter>('all');
  const { order, reorder, reset } = useOrderTableColumnOrder('closed');
  const columns = useMemo(
    () =>
      normalizeColumnOrder(order, DEFAULT_CLOSED_ORDER_COLUMNS) as ClosedOrderColumnId[],
    [order],
  );
  const headerMeta = useMemo(
    () => columns.map((id) => CLOSED_COLUMN_META[id]),
    [columns],
  );
  const rows = useMemo(
    () => filterClosedOrders(orders, filter, filterSymbol),
    [orders, filter, filterSymbol],
  );

  return (
    <div
      className="ibkr-closed-orders"
      data-testid="closed-orders-panel"
      data-module="closed_orders"
      data-sample={sampleMode ? '1' : undefined}
    >
      {!hideTitle && (
        <div className="ibkr-closed-orders-header">
          <h4 className="ibkr-section-title">{CLOSED_ORDERS_PANEL_TITLE}</h4>
          <p className="ibkr-closed-orders-hint">
            Filled and cancelled session orders. To remove a working order, use Cancel on
            Working Orders — Flatten on Positions closes the whole position.
          </p>
        </div>
      )}
      {sampleMode && (
        <div className="ibkr-sample-banner" data-testid="closed-orders-sample-banner">
          {CLOSED_ORDERS_SAMPLE_BANNER}
        </div>
      )}
      <div className="ibkr-closed-orders-filters" role="tablist" aria-label="Closed order filter">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filter === f.id}
            className={
              filter === f.id
                ? 'ibkr-closed-orders-filter active'
                : 'ibkr-closed-orders-filter'
            }
            data-filter={f.id}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="ibkr-empty">{CLOSED_ORDERS_EMPTY_MESSAGE}</div>
      ) : (
        <OrderTableDnd onReorder={reorder}>
        <table className="ibkr-table ibkr-table--orders ibkr-table--closed">
          <thead>
            <OrderTableColumnHeader columns={headerMeta} onReset={reset} />
          </thead>
          <tbody>
            {rows.map((o) => {
              const statusLabel = formatOrderStatus(
                o.status,
                o.filled_qty ?? 0,
                o.qty,
              );
              const tone = orderStatusTone(statusLabel);
              const sideCls = orderSideClass(o.side);
              const sideRowCls = orderSideRowClass(o.side);
              const ctx = {
                statusLabel,
                tone,
                activityIso: orderActivityIso(o),
                sideCls,
                sideLabel: formatOrderSide(o.side),
              };
              const cells = (
                <>{columns.map((col) => renderClosedOrderCell(col, o, ctx))}</>
              );
              if (onSelectSymbol && onOpenTrading) {
                return (
                  <SelectableTableRow
                    key={o.order_id}
                    symbol={o.symbol}
                    selected={selectedSymbol === o.symbol}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                    className={sideRowCls || undefined}
                  >
                    {cells}
                  </SelectableTableRow>
                );
              }
              return (
                <tr
                  key={o.order_id}
                  className={sideRowCls || undefined}
                  data-side={o.side}
                >
                  {cells}
                </tr>
              );
            })}
          </tbody>
        </table>
        </OrderTableDnd>
      )}
    </div>
  );
}
