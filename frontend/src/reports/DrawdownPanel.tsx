/** Equity curve summary + max drawdown (Reports v2). */
import type { DrawdownResponse } from './types';
import { fmtPnl } from './format';

interface Props {
  data: DrawdownResponse | null;
  loading: boolean;
}

export function DrawdownPanel({ data, loading }: Props) {
  if (loading && !data) {
    return <div className="reports-v2-section reports-status">Loading drawdown…</div>;
  }
  if (!data || data.trade_count === 0) {
    return (
      <div className="reports-v2-section reports-empty">
        No closed trades for drawdown analysis.
      </div>
    );
  }

  return (
    <section className="reports-v2-section">
      <h3 className="reports-v2-title">Drawdown</h3>
      <div className="reports-analytics">
        <div className="journal-metric" title="Cumulative closed-trade P&L.">
          <span className="journal-metric-label">Final equity</span>
          <span className={data.final_equity > 0 ? 'pnl-pos' : data.final_equity < 0 ? 'pnl-neg' : ''}>
            {fmtPnl(data.final_equity)}
          </span>
        </div>
        <div className="journal-metric" title="Peak cumulative equity before any pullback.">
          <span className="journal-metric-label">Peak</span>
          <span>{fmtPnl(data.peak_equity)}</span>
        </div>
        <div className="journal-metric" title="Largest peak-to-trough decline.">
          <span className="journal-metric-label">Max DD</span>
          <span className="pnl-neg">{fmtPnl(-data.max_drawdown)}</span>
        </div>
        <div className="journal-metric" title="Max drawdown as % of peak equity.">
          <span className="journal-metric-label">Max DD %</span>
          <span>
            {data.max_drawdown_pct != null ? `${data.max_drawdown_pct.toFixed(1)}%` : '—'}
          </span>
        </div>
      </div>
      {data.curve.length > 0 && (
        <div className="reports-v2-curve" aria-label="Equity curve by closed trade">
          {data.curve.map((pt, idx) => {
            const heightPct = data.peak_equity > 0
              ? Math.max(4, (pt.equity / data.peak_equity) * 100)
              : 4;
            return (
              <div
                key={`${pt.trade_id ?? idx}-${pt.closed_ts}`}
                className="reports-v2-curve-bar"
                style={{ height: `${heightPct}%` }}
                title={`${pt.symbol}: ${fmtPnl(pt.equity)}`}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}
