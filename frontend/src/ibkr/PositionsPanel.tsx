import { useMemo, type ReactNode } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { ClosePositionButton } from '../closed_orders';
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
  /** Set when the last positions/orders poll failed — disable Flatten. */
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
}

function fmt(n: number | null | undefined, decimals = 2) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtDollar(n: number | null | undefined) {
  if (n == null) return '—';
  return `$${fmt(n)}`;
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
          {fmt(p.qty, 0)}
        </td>
      );
    case 'avg_cost':
      return (
        <td key={col} className="ibkr-col--num">
          {fmtDollar(p.avg_cost)}
        </td>
      );
    case 'mkt_price':
      return (
        <td key={col} className="ibkr-col--num">
          {fmtDollar(p.market_price)}
        </td>
      );
    case 'mkt_value':
      return (
        <td key={col} className="ibkr-col--num">
          {fmtDollar(p.market_value)}
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
          {fmtDollar(p.unrealized_pnl)}
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
    <div className="ibkr-positions-panel">
      {summary && summary.connected && (
        <div className="ibkr-account-strip">
          <span><label>Net Liq</label>{fmtDollar(summary.NetLiquidation)}</span>
          <span><label>Cash</label>{fmtDollar(summary.TotalCashValue)}</span>
          <span><label>Buying Power</label>{fmtDollar(summary.BuyingPower)}</span>
          <span>
            <label>Unrealized P&L</label>
            <span
              style={{
                color: (summary.UnrealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)',
              }}
            >
              {fmtDollar(summary.UnrealizedPnL)}
            </span>
          </span>
          <span>
            <label>Realized P&L</label>
            <span
              style={{
                color: (summary.RealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)',
              }}
            >
              {fmtDollar(summary.RealizedPnL)}
            </span>
          </span>
        </div>
      )}

      <h4 className="ibkr-section-title">Positions</h4>
      {error && (
        <div className="ibkr-empty ibkr-empty--error" data-testid="positions-error">
          {error} — Flatten disabled until the poll recovers.
        </div>
      )}
      {positions.length === 0 ? (
        !error && <div className="ibkr-empty">No open positions.</div>
      ) : (
        <OrderTableDnd onReorder={reorder}>
        <table className="ibkr-table ibkr-table--orders">
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
              return (
                <SelectableTableRow
                  key={p.symbol}
                  symbol={p.symbol}
                  selected={selectedSymbol === p.symbol}
                  onSelect={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                  className={sideRowCls || undefined}
                >
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
                </SelectableTableRow>
              );
            })}
          </tbody>
        </table>
        </OrderTableDnd>
      )}

      <WorkingOrdersPanel
        orders={orders}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={onSelectSymbol}
        onOpenTrading={onOpenTrading}
        onCancelOrder={onCancelOrder}
        onFillImmediately={onFillImmediately}
        highlightOrderId={highlightOrderId}
      />
    </div>
  );
}
