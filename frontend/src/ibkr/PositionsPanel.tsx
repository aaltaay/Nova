import { useMemo, type ReactNode } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { ClosePositionButton } from '../closed_orders';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { OrderTableColumnHeader, OrderTableDnd } from './OrderTableColumnHeader';
import { positionSideClass, positionSideRowClass } from './orderDisplay';
import {
  DEFAULT_POSITION_COLUMNS,
  POSITION_COLUMN_META,
  normalizeColumnOrder,
  type PositionColumnId,
} from './orderTableColumns';
import type { IbkrPosition, IbkrOrder, IbkrAccountSummary, IbkrMode } from './types';
import { useOrderTableColumnOrder } from './useOrderTableColumnOrder';
import { WorkingOrdersPanel } from './WorkingOrdersPanel';

interface Props {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  /** Set when the last positions/orders poll failed — rows above are
   * last-good, not an honest "flat" read. */
  error?: string | null;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  onCancelOrder?: (id: number) => void;
  onFillImmediately?: (order: IbkrOrder) => void;
  highlightOrderId?: number | null;
  mode?: IbkrMode;
  connected?: boolean;
  spendStatus?: string;
  onPositionClosed?: () => void;
  /** Stock View dock: table only (no account strip / nested Working Orders). */
  compact?: boolean;
  hideTitle?: boolean;
}

function renderPositionCell(
  col: PositionColumnId,
  p: IbkrPosition,
  sideCls: string,
  sideTitle: string | undefined,
): ReactNode {
  switch (col) {
    case 'symbol':
      return (
        <td key={col} className={`ibkr-col--text ibkr-symbol ${sideCls}`} title={sideTitle}>
          {p.symbol}
        </td>
      );
    case 'qty':
      return (
        <td key={col} className={`ibkr-col--num ${sideCls}`} title={sideTitle}>
          {formatShareQty(p.qty)}
        </td>
      );
    case 'avg_cost':
      return (
        <td key={col} className="ibkr-col--num">
          {formatMoney(p.avg_cost)}
        </td>
      );
    case 'mkt_price':
      return (
        <td key={col} className="ibkr-col--num">
          {formatMoney(p.market_price)}
        </td>
      );
    case 'mkt_value':
      return (
        <td key={col} className="ibkr-col--num">
          {formatMoney(p.market_value)}
        </td>
      );
    case 'unrealized': {
      const color =
        p.unrealized_pnl == null
          ? undefined
          : p.unrealized_pnl >= 0
            ? 'var(--green)'
            : 'var(--red)';
      return (
        <td key={col} className="ibkr-col--num" style={{ color }}>
          {formatMoney(p.unrealized_pnl)}
        </td>
      );
    }
    default:
      return null;
  }
}

export function PositionsPanel({
  summary,
  positions,
  orders,
  error = null,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  onCancelOrder,
  onFillImmediately,
  highlightOrderId = null,
  mode = 'disconnected',
  connected = false,
  spendStatus,
  onPositionClosed,
  compact = false,
  hideTitle = false,
}: Props) {
  const showFlatten = connected && mode !== 'disconnected';
  const { order, reorder, reset } = useOrderTableColumnOrder('positions');
  const columns = useMemo(
    () =>
      normalizeColumnOrder(order, DEFAULT_POSITION_COLUMNS) as PositionColumnId[],
    [order],
  );
  const headerMeta = useMemo(
    () => columns.map((id) => POSITION_COLUMN_META[id]),
    [columns],
  );

  return (
    <div
      className={`ibkr-positions-panel${compact ? ' ibkr-positions-panel--compact' : ''}`}
      data-testid="positions-panel"
    >
      {!compact && summary && summary.connected && (
        <div className="ibkr-account-strip">
          <span><label>Net Liq</label>{formatMoney(summary.NetLiquidation)}</span>
          <span><label>Cash</label>{formatMoney(summary.TotalCashValue)}</span>
          <span><label>Buying Power</label>{formatMoney(summary.BuyingPower)}</span>
          <span>
            <label>Unrealized P&L</label>
            <span
              style={{
                color: (summary.UnrealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)',
              }}
            >
              {formatMoney(summary.UnrealizedPnL)}
            </span>
          </span>
          <span>
            <label>Realized P&L</label>
            <span
              style={{
                color: (summary.RealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)',
              }}
            >
              {formatMoney(summary.RealizedPnL)}
            </span>
          </span>
        </div>
      )}

      {!hideTitle && <h4 className="ibkr-section-title">Positions</h4>}
      {error && (
        <div className="ibkr-empty ibkr-empty--error" data-testid="positions-error">
          {error} — showing last-known data.
        </div>
      )}
      {positions.length === 0 ? (
        !error && (
          <div className="ibkr-empty" data-testid="positions-empty">
            No open positions.
          </div>
        )
      ) : (
        <OrderTableDnd onReorder={reorder}>
        <table className="ibkr-table ibkr-table--orders" data-testid="positions-table">
          <thead>
            <OrderTableColumnHeader
              columns={headerMeta}
              onReset={reset}
              trailing={
                showFlatten ? (
                  <th
                    className="ibkr-col--actions"
                    data-column-pinned="close"
                    title="Full position exit — not cancel order"
                  >
                    Close
                  </th>
                ) : null
              }
            />
          </thead>
          <tbody>
            {positions.map((p) => {
              const sideCls = positionSideClass(p.qty);
              const sideRowCls = positionSideRowClass(p.qty);
              const sideTitle = p.qty > 0 ? 'Long' : p.qty < 0 ? 'Short' : undefined;
              const cells = (
                <>
                  {columns.map((col) => renderPositionCell(col, p, sideCls, sideTitle))}
                  {showFlatten ? (
                    <td className="ibkr-col--actions">
                      <ClosePositionButton
                        position={p}
                        mode={mode}
                        connected={connected}
                        spendStatus={spendStatus}
                        disabled={Boolean(error)}
                        onClosed={onPositionClosed}
                      />
                    </td>
                  ) : null}
                </>
              );
              if (onSelectSymbol && onOpenTrading) {
                return (
                  <SelectableTableRow
                    key={p.symbol}
                    symbol={p.symbol}
                    selected={selectedSymbol === p.symbol}
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
                  key={p.symbol}
                  className={sideRowCls || undefined}
                  data-symbol={p.symbol}
                >
                  {cells}
                </tr>
              );
            })}
          </tbody>
        </table>
        </OrderTableDnd>
      )}

      {!compact && (
        <WorkingOrdersPanel
          orders={orders}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
          onCancelOrder={onCancelOrder}
          onFillImmediately={onFillImmediately}
          highlightOrderId={highlightOrderId}
          error={error}
        />
      )}
    </div>
  );
}
