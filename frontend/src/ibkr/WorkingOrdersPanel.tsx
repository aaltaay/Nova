/**
 * Working Orders table — Webull Orders → Working equivalent (WID-026).
 * Cancel / Fill now; column order drag-persisted (localStorage).
 */
import { useMemo } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import {
  FILL_WORKING_ORDER_BUTTON_LABEL,
  FILL_WORKING_ORDER_BUTTON_TITLE,
  WORKING_ORDERS_PANEL_TITLE,
} from '../constants';
import { OrderTableColumnHeader, OrderTableDnd } from './OrderTableColumnHeader';
import {
  formatOrderSide,
  formatOrderStatus,
  orderActivityIso,
  orderSideClass,
  orderSideRowClass,
  orderStatusTone,
} from './orderDisplay';
import { WORKING_COLUMN_META, visibleWorkingColumns } from './orderTableColumns';
import type { IbkrOrder } from './types';
import { useOrderTableColumnOrder } from './useOrderTableColumnOrder';
import { renderWorkingOrderCell } from './workingOrderCells';

interface Props {
  orders: IbkrOrder[];
  selectedSymbol?: string | null;
  onSelectSymbol?: (symbol: string) => void;
  onOpenTrading?: (symbol: string) => void;
  onCancelOrder?: (id: number) => void;
  onFillImmediately?: (order: IbkrOrder) => void;
  highlightOrderId?: number | null;
  filterSymbol?: string | null;
  hideTitle?: boolean;
  compact?: boolean;
}

function remainingQty(o: IbkrOrder): number {
  if (o.remaining_qty != null && Number.isFinite(o.remaining_qty)) {
    return Math.max(0, o.remaining_qty);
  }
  return Math.max(0, o.qty - (o.filled_qty ?? 0));
}

export function WorkingOrdersPanel({
  orders,
  selectedSymbol = null,
  onSelectSymbol,
  onOpenTrading,
  onCancelOrder,
  onFillImmediately,
  highlightOrderId = null,
  filterSymbol = null,
  hideTitle = false,
  compact = false,
}: Props) {
  const { order, reorder, reset } = useOrderTableColumnOrder('working');
  const columns = useMemo(
    () => visibleWorkingColumns(order, compact),
    [order, compact],
  );
  const headerMeta = useMemo(
    () => columns.map((id) => WORKING_COLUMN_META[id]),
    [columns],
  );

  const filterKey = filterSymbol?.toUpperCase() ?? null;
  const rows = filterKey
    ? orders.filter((o) => o.symbol.toUpperCase() === filterKey)
    : orders;
  const showActions = Boolean(onCancelOrder || onFillImmediately);

  return (
    <div
      className={`ibkr-working-orders${compact ? ' ibkr-working-orders--compact' : ''}`}
      data-testid="working-orders-panel"
      data-highlight-order={highlightOrderId ?? undefined}
    >
      {!hideTitle && (
        <h4 className="ibkr-section-title">{WORKING_ORDERS_PANEL_TITLE}</h4>
      )}
      {rows.length === 0 ? (
        <div className="ibkr-empty">No open orders.</div>
      ) : (
        <OrderTableDnd onReorder={reorder}>
        <table className="ibkr-table ibkr-table--orders">
          <thead>
            <OrderTableColumnHeader
              columns={headerMeta}
              onReset={reset}
              trailing={
                showActions ? (
                  <th className="ibkr-col--actions" data-column-pinned="actions">
                    Actions
                  </th>
                ) : null
              }
            />
          </thead>
          <tbody>
            {rows.map((o) => {
              const highlighted = highlightOrderId === o.order_id;
              const statusLabel = formatOrderStatus(
                o.status,
                o.filled_qty ?? 0,
                o.qty,
              );
              const tone = orderStatusTone(statusLabel);
              const rem = remainingQty(o);
              const sideCls = orderSideClass(o.side);
              const sideRowCls = orderSideRowClass(o.side);
              const rowClass = [sideRowCls, highlighted ? 'ibkr-order-row--highlight' : '']
                .filter(Boolean)
                .join(' ');
              const ctx = {
                statusLabel,
                tone,
                activityIso: orderActivityIso(o),
                sideCls,
                sideLabel: formatOrderSide(o.side),
              };
              const cells = (
                <>
                  {columns.map((col) => renderWorkingOrderCell(col, o, ctx))}
                  {showActions ? (
                    <td className="ibkr-col--actions">
                      <div className="ibkr-order-actions">
                        {onFillImmediately ? (
                          <button
                            type="button"
                            className="ibkr-fill-now-btn"
                            disabled={rem <= 0}
                            onClick={(e) => {
                              e.stopPropagation();
                              onFillImmediately(o);
                            }}
                            title={FILL_WORKING_ORDER_BUTTON_TITLE}
                            aria-label={`${FILL_WORKING_ORDER_BUTTON_LABEL} order ${o.order_id}`}
                          >
                            {FILL_WORKING_ORDER_BUTTON_LABEL}
                          </button>
                        ) : null}
                        {onCancelOrder ? (
                          <button
                            type="button"
                            className="ibkr-cancel-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              onCancelOrder(o.order_id);
                            }}
                            title="Cancel resting order (does not reverse fills)"
                            aria-label={`Cancel order ${o.order_id}`}
                          >
                            Cancel
                          </button>
                        ) : null}
                      </div>
                    </td>
                  ) : null}
                </>
              );

              if (onSelectSymbol && onOpenTrading) {
                return (
                  <SelectableTableRow
                    key={o.order_id}
                    symbol={o.symbol}
                    selected={selectedSymbol === o.symbol || highlighted}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                    className={rowClass || undefined}
                  >
                    {cells}
                  </SelectableTableRow>
                );
              }

              return (
                <tr
                  key={o.order_id}
                  className={rowClass || undefined}
                  data-order-id={o.order_id}
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
