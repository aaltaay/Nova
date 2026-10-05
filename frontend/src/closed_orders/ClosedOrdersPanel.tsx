/**
 * Closed Orders — Webull History / filled+cancelled lifecycle (WID-027).
 * Column order drag-persisted (shared localStorage with Working Orders).
 */
import { useEffect, useMemo, useReducer, useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import {
  CLOSED_ORDERS_EMPTY_MESSAGE,
  CLOSED_ORDERS_PANEL_TITLE,
  CLOSED_ORDERS_RECENT_EXPIRY_SLACK_MS,
  CLOSED_ORDERS_RECENT_HIGHLIGHT_MS,
  CLOSED_ORDERS_RECENT_ROW_TITLE,
  CLOSED_ORDERS_SAMPLE_BANNER,
} from '../constants';
import { lastKnownBanner } from '../ibkr/disconnectCopy';
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
import { displayFilledQty } from '../ibkr/orderFillHonesty';
import { orderRowKeys } from '../ibkr/orderIdentity';
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
  // Read at every render; a timer below renders once more when the newest highlight runs out.
  const nowMs = Date.now();
  const [, expireHighlight] = useReducer((n: number) => n + 1, 0);
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
  // Not order_id: completed IB orders replay as orderId 0 (C29).
  const rowKeys = useMemo(() => orderRowKeys(rows), [rows]);

  // When the next highlighted row stops being recent (null: none is highlighted).
  let nextHighlightEndsAt: number | null = null;
  for (const o of rows) {
    const activityIso = orderActivityIso(o);
    if (!isClosedOrderRecent(activityIso, nowMs, CLOSED_ORDERS_RECENT_HIGHLIGHT_MS)) continue;
    const endsAt = Date.parse(activityIso as string) + CLOSED_ORDERS_RECENT_HIGHLIGHT_MS;
    if (nextHighlightEndsAt === null || endsAt < nextHighlightEndsAt) nextHighlightEndsAt = endsAt;
  }

  useEffect(() => {
    if (nextHighlightEndsAt === null) return undefined;
    const id = window.setTimeout(
      expireHighlight,
      Math.max(0, nextHighlightEndsAt - Date.now()) + CLOSED_ORDERS_RECENT_EXPIRY_SLACK_MS,
    );
    return () => window.clearTimeout(id);
  }, [nextHighlightEndsAt]);

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
          {lastKnownBanner(error)}
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
            {rows.map((o, rowIndex) => {
              const statusLabel = formatOrderStatus(
                o.status,
                displayFilledQty(o),
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
                    key={rowKeys[rowIndex]}
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
                  key={rowKeys[rowIndex]}
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
