/** Per-tag win rate and P&L table (Reports v2); on Paper a tag's row counts the trades the pick shows (ADR 072). */
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import type { TagPerformanceRow, TagsResponse } from './types';
import { REPORTS_TAGS_EMPTY_PAPER, REPORTS_TAGS_PAPER_HINT, REPORTS_TAGS_TITLE } from './booksConstants';
import { fmtPct, fmtPnl } from './format';

interface Props {
  data: TagsResponse | null;
  loading: boolean;
  /** Paper's round trips by holder (mockup reports-v1 item 6). */
  books?: boolean;
}

const NO_TAGS: TagPerformanceRow[] = [];

const COLUMNS: SortColumns<TagPerformanceRow> = {
  tag: r => r.tag,
  trades: r => r.count,
  winRate: r => r.win_rate_pct,
  pnl: r => r.pnl,
};

export function TagPerformance({ data, loading, books = false }: Props) {
  const { rows, sort, onSort } = useTableSort('reports.tags', data?.tags ?? NO_TAGS, COLUMNS);
  if (loading && !data) {
    return <div className="reports-v2-section reports-status">Loading tag analytics…</div>;
  }
  if ((!data || data.count === 0) && books) {
    return (
      <section className="reports-v2-section" data-testid="reports-tags-paper-empty">
        <h3 className="reports-v2-title">{REPORTS_TAGS_TITLE}</h3>
        <div className="reports-empty">{REPORTS_TAGS_EMPTY_PAPER}</div>
        <p className="reports-v2-hint">{REPORTS_TAGS_PAPER_HINT}</p>
      </section>
    );
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
            <SortTh col="tag" sort={sort} onSort={onSort}>Tag</SortTh>
            <SortTh col="trades" sort={sort} onSort={onSort}>Trades</SortTh>
            <SortTh col="winRate" sort={sort} onSort={onSort}>Win rate</SortTh>
            <SortTh col="pnl" sort={sort} onSort={onSort}>P&amp;L</SortTh>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
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
