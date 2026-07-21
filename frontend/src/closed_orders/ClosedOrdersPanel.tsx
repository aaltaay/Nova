/**
 * Closed Orders — Webull History / filled+cancelled lifecycle (WID-027).
 * Column order drag-persisted (shared localStorage with Working Orders).
 */
import { useEffect, useMemo, useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import {
  CLOSED_ORDERS_EMPTY_MESSAGE,
  CLOSED_ORDERS_PANEL_TITLE,
  CLOSED_ORDERS_RECENT_HIGHLIGHT_MS,
  CLOSED_ORDERS_RECENT_ROW_TITLE,
  CLOSED_ORDERS_RECENT_TICK_MS,
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
  orderSubmittedIso,
} from '../ibkr/orderDisplay';
import {
  CLOSED_COLUMN_META,
  DEFAULT_CLOSED_ORDER_COLUMNS,
  normalizeColumnOrder,
  type ClosedOrderColumnId,
} from '../ibkr/orderTableColumns';
import { sortOrders } from '../ibkr/orderTableSort';
import { useOrderTableColumnOrder } from '../ibkr/useOrderTableColumnOrder';
import { useOrderTableSort } from '../ibkr/useOrderTableSort';
import { isClosedOrderRecent } from './closedOrderRecency';
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
  /** Hide local All/Filled/… tabs when parent owns Orders (Today) segments. */
  hideFilters?: boolean;
  /** Controlled status filter (defaults to internal All). */
  statusFilter?: ClosedOrdersFilter;
  /** Set when the last closed-orders poll failed — rows above are
   * last-good, not an honest "no closed orders" read. */
  error?: string | null;
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
  hideFilters = false,
  statusFilter,
  error = null,
}: Props) {
  const [internalFilter, setInternalFilter] = useState<ClosedOrdersFilter>('all');
  const filter = statusFilter ?? internalFilter;
  const [nowMs, setNowMs] = useState(() => Date.now());
  const { order, reorder, reset } = useOrderTableColumnOrder('closed');
  const { sortState, onSortColumn, clearSort } = useOrderTableSort('closed');
  const columns = useMemo(
    () =>
      normalizeColumnOrder(order, DEFAULT_CLOSED_ORDER_COLUMNS) as ClosedOrderColumnId[],
    [order],
  );
  const headerMeta = useMemo(
    () => columns.map((id) => CLOSED_COLUMN_META[id]),
    [columns],
  );
  const rows = useMemo(() => {
    const filtered = filterClosedOrders(orders, filter, filterSymbol);
    return sortOrders(filtered, sortState, 'closed');
  }, [orders, filter, filterSymbol, sortState]);

  useEffect(() => {
    const id = window.setInterval(
      () => setNowMs(Date.now()),
      CLOSED_ORDERS_RECENT_TICK_MS,
    );
    return () => window.clearInterval(id);
  }, []);

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
      {!hideFilters && (
        <div
          className="ibkr-closed-orders-filters"
          role="tablist"
          aria-label="Closed order filter"
        >
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
              onClick={() => setInternalFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}
      {error && (
        <div className="ibkr-empty ibkr-empty--error" data-testid="closed-orders-error">
          {error} — showing last-known data.
        </div>
      )}
      {rows.length === 0 ? (
        !error && <div className="ibkr-empty">{CLOSED_ORDERS_EMPTY_MESSAGE}</div>
      ) : (
        <OrderTableDnd onReorder={reorder}>
        <table className="ibkr-table ibkr-table--orders ibkr-table--closed">
          <thead>
            <OrderTableColumnHeader
              columns={headerMeta}
              onReset={reset}
              sortState={sortState}
              onSortColumn={onSortColumn}
              onClearSort={clearSort}
            />
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
              const activityIso = orderActivityIso(o);
              const placedIso = orderSubmittedIso(o);
              const recent = isClosedOrderRecent(
                activityIso,
                nowMs,
                CLOSED_ORDERS_RECENT_HIGHLIGHT_MS,
              );
              const rowClass = [sideRowCls, recent ? 'ibkr-order-row--recent' : '']
                .filter(Boolean)
                .join(' ');
              const ctx = {
                statusLabel,
                tone,
                placedIso,
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
                    className={rowClass || undefined}
                    hintPrefix={recent ? CLOSED_ORDERS_RECENT_ROW_TITLE : undefined}
                    dataRecent={recent}
                  >
                    {cells}
                  </SelectableTableRow>
                );
              }
              return (
                <tr
                  key={o.order_id}
                  className={rowClass || undefined}
                  data-side={o.side}
                  data-recent={recent ? '1' : undefined}
                  title={recent ? CLOSED_ORDERS_RECENT_ROW_TITLE : undefined}
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
