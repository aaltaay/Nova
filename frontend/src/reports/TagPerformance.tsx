/** Per-tag win rate and P&L table (Reports v2). */
import type { TagsResponse } from './types';
import { fmtPct, fmtPnl } from './format';

interface Props {
  data: TagsResponse | null;
  loading: boolean;
}

export function TagPerformance({ data, loading }: Props) {
  if (loading && !data) {
    return <div className="reports-v2-section reports-status">Loading tag analytics…</div>;
  }
  if (!data || data.count === 0) {
    return (
      <div className="reports-v2-section reports-empty">
        No tagged trades yet — add tags via POST /api/journal/trades/&#123;id&#125;/tags.
      </div>
    );
  }

  return (
    <section className="reports-v2-section">
      <h3 className="reports-v2-title">Tag performance</h3>
      <table className="reports-v2-table">
        <thead>
          <tr>
            <th>Tag</th>
            <th>Trades</th>
            <th>Win rate</th>
            <th>P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {data.tags.map(row => (
            <tr key={row.tag}>
              <td>{row.tag}</td>
              <td>{row.count}</td>
              <td>{fmtPct(row.win_rate_pct)}</td>
              <td className={row.pnl > 0 ? 'pnl-pos' : row.pnl < 0 ? 'pnl-neg' : ''}>
                {fmtPnl(row.pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
