import type { IbkrPosition, IbkrOrder, IbkrAccountSummary } from './types';

interface Props {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  onCancelOrder?: (id: number) => void;
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

export function PositionsPanel({ summary, positions, orders, onCancelOrder }: Props) {
  return (
    <div className="ibkr-positions-panel">
      {/* Account summary strip */}
      {summary && summary.connected && (
        <div className="ibkr-account-strip">
          <span><label>Net Liq</label>{fmtDollar(summary.NetLiquidation)}</span>
          <span><label>Cash</label>{fmtDollar(summary.TotalCashValue)}</span>
          <span><label>Buying Power</label>{fmtDollar(summary.BuyingPower)}</span>
          <span><label>Unrealized P&L</label><span style={{ color: (summary.UnrealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtDollar(summary.UnrealizedPnL)}</span></span>
          <span><label>Realized P&L</label><span style={{ color: (summary.RealizedPnL ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtDollar(summary.RealizedPnL)}</span></span>
        </div>
      )}

      {/* Positions table */}
      <h4 className="ibkr-section-title">Positions</h4>
      {positions.length === 0 ? (
        <div className="ibkr-empty">No open positions.</div>
      ) : (
        <table className="ibkr-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Avg Cost</th>
              <th>Mkt Price</th>
              <th>Mkt Value</th>
              <th>Unrealized P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(p => (
              <tr key={p.symbol}>
                <td className="ibkr-symbol">{p.symbol}</td>
                <td>{fmt(p.qty, 0)}</td>
                <td>{fmtDollar(p.avg_cost)}</td>
                <td>{fmtDollar(p.market_price)}</td>
                <td>{fmtDollar(p.market_value)}</td>
                <PnlCell value={p.unrealized_pnl} />
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Open orders table */}
      <h4 className="ibkr-section-title">Open Orders</h4>
      {orders.length === 0 ? (
        <div className="ibkr-empty">No open orders.</div>
      ) : (
        <table className="ibkr-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Type</th>
              <th>Limit</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {orders.map(o => (
              <tr key={o.order_id}>
                <td>{o.order_id}</td>
                <td className="ibkr-symbol">{o.symbol}</td>
                <td style={{ color: o.side === 'BUY' ? 'var(--green)' : 'var(--red)' }}>{o.side}</td>
                <td>{fmt(o.qty, 0)}</td>
                <td>{o.order_type}</td>
                <td>{fmtDollar(o.limit_price)}</td>
                <td>{o.status}</td>
                <td>
                  <button
                    className="ibkr-cancel-btn"
                    onClick={() => onCancelOrder?.(o.order_id)}
                    title="Cancel order"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
