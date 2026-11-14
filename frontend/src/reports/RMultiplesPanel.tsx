/** R-multiple expectancy summary (Reports v2); Paper's All view adds the four books, in order (ADR 072). */
import { OWNERS } from '../constantGroups/owners';
import type { RBookSummary, RMultiplesResponse } from './types';
import { REPORTS_R_PAPER_STOP, reportsRPaperStops } from './booksConstants';
import { fmtRMultiple } from './format';
import { figureSplit, type SplitFigure } from './reportsView';
import { SplitLine } from './SplitLine';

interface Props {
  data: RMultiplesResponse | null;
  loading: boolean;
  /** Paper's round trips by holder: the hint says where a Paper trade's stop comes from. */
  books?: boolean;
}

const rFigure = (r: number | null): SplitFigure | null => (r == null ? null : { text: fmtRMultiple(r), value: r });
const scored = (book: RBookSummary): SplitFigure | null =>
  book.trade_count > 0 ? { text: `${book.scored_count} / ${book.trade_count}`, value: null } : null;

/** Where a Paper trade's stop comes from, with how many of each book's trades sent none on All. */
function paperStops(data: RMultiplesResponse): string {
  const split = data.by_owner;
  if (!split) return `${REPORTS_R_PAPER_STOP}.`;
  return reportsRPaperStops(OWNERS.filter((owner) => split[owner]).map((owner) => ({
    owner, skipped: split[owner].skipped_no_stop, n: split[owner].trade_count,
  })));
}

export function RMultiplesPanel({ data, loading, books = false }: Props) {
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
          <SplitLine stacked split={figureSplit(data.by_owner, (b) => rFigure(b.expectancy_r))} />
        </div>
        <div className="journal-metric" title="Trades scored vs skipped (no stop).">
          <span className="journal-metric-label">Scored</span>
          <span>
            {data.scored_count} / {data.trade_count}
          </span>
          <SplitLine stacked split={figureSplit(data.by_owner, scored)} />
        </div>
        <div className="journal-metric" title="Average R on winning trades.">
          <span className="journal-metric-label">Avg win R</span>
          <span className="pnl-pos">{fmtRMultiple(data.avg_win_r)}</span>
          <SplitLine stacked split={figureSplit(data.by_owner, (b) => rFigure(b.avg_win_r))} />
        </div>
        <div className="journal-metric" title="Average R on losing trades.">
          <span className="journal-metric-label">Avg loss R</span>
          <span className="pnl-neg">{fmtRMultiple(data.avg_loss_r)}</span>
          <SplitLine stacked split={figureSplit(data.by_owner, (b) => rFigure(b.avg_loss_r))} />
        </div>
      </div>
      {data.skipped_no_stop > 0 && (
        <p className="reports-v2-hint" data-testid="reports-r-hint">
          {data.skipped_no_stop} trade(s) skipped — no stop price on file.
          {books && ` ${paperStops(data)}`}
        </p>
      )}
    </section>
  );
}
