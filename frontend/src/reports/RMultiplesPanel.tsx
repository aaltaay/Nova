/** R-multiple expectancy summary (Reports v2). */
import type { RMultiplesResponse } from './types';
import { fmtRMultiple } from './format';

interface Props {
  data: RMultiplesResponse | null;
  loading: boolean;
}

export function RMultiplesPanel({ data, loading }: Props) {
  if (loading && !data) {
    return <div className="reports-v2-section reports-status">Loading R-multiples…</div>;
  }
  if (!data || data.trade_count === 0) {
    return (
      <div className="reports-v2-section reports-empty">
        No closed trades for R-multiple analysis.
      </div>
    );
  }

  return (
    <section className="reports-v2-section">
      <h3 className="reports-v2-title">R-multiples</h3>
      <div className="reports-analytics">
        <div className="journal-metric" title="Average R across trades with a planned stop.">
          <span className="journal-metric-label">Expectancy</span>
          <span>{fmtRMultiple(data.expectancy_r)}</span>
        </div>
        <div className="journal-metric" title="Trades scored vs skipped (no stop).">
          <span className="journal-metric-label">Scored</span>
          <span>
            {data.scored_count} / {data.trade_count}
          </span>
        </div>
        <div className="journal-metric" title="Average R on winning trades.">
          <span className="journal-metric-label">Avg win R</span>
          <span className="pnl-pos">{fmtRMultiple(data.avg_win_r)}</span>
        </div>
        <div className="journal-metric" title="Average R on losing trades.">
          <span className="journal-metric-label">Avg loss R</span>
          <span className="pnl-neg">{fmtRMultiple(data.avg_loss_r)}</span>
        </div>
      </div>
      {data.skipped_no_stop > 0 && (
        <p className="reports-v2-hint">
          {data.skipped_no_stop} trade(s) skipped — no stop price on file.
        </p>
      )}
    </section>
  );
}
