/** Year-level growth summary (Win vs Loss Days lite). */
import type { YearCalendarResponse } from './types';
import { fmtPnl } from './format';

interface Props {
  data: YearCalendarResponse;
}

export function AnalyticsSummary({ data }: Props) {
  return (
    <div className="reports-analytics">
      <div className="journal-metric" title="Sum of all closed-trade P&L in this calendar year (ET).">
        <span className="journal-metric-label">Year P&amp;L</span>
        <span className={data.year_pnl > 0 ? 'pnl-pos' : data.year_pnl < 0 ? 'pnl-neg' : ''}>
          {fmtPnl(data.year_pnl)}
        </span>
      </div>
      <div className="journal-metric" title="Closed trades counted in this year.">
        <span className="journal-metric-label">Trades</span>
        <span>{data.year_trade_count}</span>
      </div>
      <div className="journal-metric" title="Calendar days with net P&L &gt; 0.">
        <span className="journal-metric-label">Winning days</span>
        <span className="pnl-pos">{data.winning_days}</span>
      </div>
      <div className="journal-metric" title="Calendar days with net P&L &lt; 0.">
        <span className="journal-metric-label">Losing days</span>
        <span className="pnl-neg">{data.losing_days}</span>
      </div>
      <div className="journal-metric" title="Best single day by net P&L.">
        <span className="journal-metric-label">Best day</span>
        <span>
          {data.best_day
            ? `${data.best_day.date} (${fmtPnl(data.best_day.pnl)})`
            : '—'}
        </span>
      </div>
      <div className="journal-metric" title="Worst single day by net P&L.">
        <span className="journal-metric-label">Worst day</span>
        <span>
          {data.worst_day
            ? `${data.worst_day.date} (${fmtPnl(data.worst_day.pnl)})`
            : '—'}
        </span>
      </div>
    </div>
  );
}
