import type { IbkrPosition, IbkrOrder, IbkrAccountSummary, IbkrMode } from './types';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { ClosePositionButton } from '../closed_orders';
import { WorkingOrdersPanel } from './WorkingOrdersPanel';

interface Props {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  onCancelOrder?: (id: number) => void;
  highlightOrderId?: number | null;
  /** Required for Flatten affordance (ADR 007 place path). */
  mode?: IbkrMode;
  connected?: boolean;
  spendStatus?: string;
  onPositionClosed?: () => void;
}

function fmt(n: number | null | undefined, decimals = 2) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtDollar(n: number | null | undefined) {
  if (n == null) return '—';
  return `$${fmt(n)}`;
}

function PnlCell({ value }: { value: number | null | undefined }) {
  const color = value == null ? undefined : value >= 0 ? 'var(--green)' : 'var(--red)';
  return <td style={{ color }}>{fmtDollar(value)}</td>;
}

export function PositionsPanel({
  summary,
  positions,
  orders,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  onCancelOrder,
  highlightOrderId = null,
  mode = 'disconnected',
  connected = false,
  spendStatus,
  onPositionClosed,
}: Props) {
  const showFlatten = connected && mode !== 'disconnected';

  return (
    <div className="ibkr-positions-panel">
      {summary && summary.connected && (
        <div className="ibkr-account-strip">
          <span><label>Net Liq</label>{fmtDollar(summary.NetLiquidation)}</span>
          <span><label>Cash</label>{fmtDollar(summary.TotalCashValue)}</span>
          <span><label>Buying Power</label>{fmtDollar(summary.BuyingPower)}</span>
          <span><label>Unrealized P&L</label><span style={{ color: (summary.UnrealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtDollar(summary.UnrealizedPnL)}</span></span>
          <span><label>Realized P&L</label><span style={{ color: (summary.RealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtDollar(summary.RealizedPnL)}</span></span>
        </div>
      )}

      <h4 className="ibkr-section-title">Positions</h4>
      {positions.length === 0 ? (
        <div className="ibkr-empty">No open positions.</div>
      ) : (
        <table className="ibkr-table">
          <thead>
            <tr>
              <th title="Click: Quote Panel · Double-click: Stock View">Symbol</th>
              <th>Qty</th>
              <th>Avg Cost</th>
              <th>Mkt Price</th>
              <th>Mkt Value</th>
              <th>Unrealized P&L</th>
              {showFlatten ? <th title="Full position exit — not cancel order">Close</th> : null}
            </tr>
          </thead>
          <tbody>
            {positions.map(p => (
              <SelectableTableRow
                key={p.symbol}
                symbol={p.symbol}
                selected={selectedSymbol === p.symbol}
                onSelect={onSelectSymbol}
                onOpenTrading={onOpenTrading}
              >
                <td className="ibkr-symbol">{p.symbol}</td>
                <td>{fmt(p.qty, 0)}</td>
                <td>{fmtDollar(p.avg_cost)}</td>
                <td>{fmtDollar(p.market_price)}</td>
                <td>{fmtDollar(p.market_value)}</td>
                <PnlCell value={p.unrealized_pnl} />
                {showFlatten ? (
                  <td>
                    <ClosePositionButton
                      position={p}
                      mode={mode}
                      connected={connected}
                      spendStatus={spendStatus}
                      onClosed={onPositionClosed}
                    />
                  </td>
                ) : null}
              </SelectableTableRow>
            ))}
          </tbody>
        </table>
      )}

      <WorkingOrdersPanel
        orders={orders}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={onSelectSymbol}
        onOpenTrading={onOpenTrading}
        onCancelOrder={onCancelOrder}
        highlightOrderId={highlightOrderId}
      />
    </div>
  );
}
