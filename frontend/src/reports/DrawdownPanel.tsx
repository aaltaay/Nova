/**
 * Equity curve summary + max drawdown (Reports v2). Each bar is the running P&L after one closed trade, drawn
 * between the curve's lowest point and its highest; on Paper it is coloured by whose trade it was and the All
 * view adds yours and the bots' beside each figure (ADR 069, mockup reports-v1 item 8).
 */
import { whoName } from '../account';
import type { DrawdownBookSummary, DrawdownResponse } from './types';
import { REPORTS_DRAWDOWN_PAPER_HINT } from './booksConstants';
import { fmtPnl } from './format';
import { figureSplit, type SplitFigure } from './reportsView';
import { SplitLine } from './SplitLine';

interface Props {
  data: DrawdownResponse | null;
  loading: boolean;
  /** Paper's round trips by holder: bars coloured by whose trade. */
  books?: boolean;
}

/** The shortest bar, so the curve's lowest point still shows. */
const CURVE_MIN_PCT = 3;
/** The share of each trade's slot left empty between bars; it scales with the slot, so any count fits. */
const CURVE_GAP = 0.2;

/** Each bar's height in percent: the running P&L between the curve's lowest point and its highest. */
export function curveHeights(equity: number[]): number[] {
  if (equity.length === 0) return [];
  const lo = Math.min(...equity);
  const span = Math.max(...equity) - lo || 1;
  return equity.map((e) => Math.max(CURVE_MIN_PCT, ((e - lo) / span) * 100));
}

const ifTraded = (pick: (b: DrawdownBookSummary) => SplitFigure | null) =>
  (b: DrawdownBookSummary): SplitFigure | null => (b.trade_count > 0 ? pick(b) : null);

export function DrawdownPanel({ data, loading, books = false }: Props) {
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
  const heights = curveHeights(data.curve.map((pt) => pt.equity));

  return (
    <section className="reports-v2-section">
      <h3 className="reports-v2-title">Drawdown</h3>
      <div className="reports-analytics">
        <div className="journal-metric" title="Cumulative closed-trade P&L.">
          <span className="journal-metric-label">Final equity</span>
          <span className={data.final_equity > 0 ? 'pnl-pos' : data.final_equity < 0 ? 'pnl-neg' : ''}>
            {fmtPnl(data.final_equity)}
          </span>
          <SplitLine stacked split={figureSplit(data.by_owner, ifTraded((b) => ({ text: fmtPnl(b.final_equity), value: b.final_equity })))} />
        </div>
        <div className="journal-metric" title="Peak cumulative equity before any pullback.">
          <span className="journal-metric-label">Peak</span>
          <span>{fmtPnl(data.peak_equity)}</span>
          <SplitLine stacked split={figureSplit(data.by_owner, ifTraded((b) => ({ text: fmtPnl(b.peak_equity), value: null })))} />
        </div>
        <div className="journal-metric" title="Largest peak-to-trough decline.">
          <span className="journal-metric-label">Max DD</span>
          <span className="pnl-neg">{fmtPnl(-data.max_drawdown)}</span>
          <SplitLine stacked split={figureSplit(data.by_owner, ifTraded((b) => ({ text: fmtPnl(-b.max_drawdown), value: -b.max_drawdown })))} />
        </div>
        <div className="journal-metric" title="Max drawdown as % of peak equity.">
          <span className="journal-metric-label">Max DD %</span>
          <span>
            {data.max_drawdown_pct != null ? `${data.max_drawdown_pct.toFixed(1)}%` : '—'}
          </span>
          <SplitLine stacked split={figureSplit(data.by_owner, ifTraded((b) =>
            b.max_drawdown_pct == null ? null : { text: `${b.max_drawdown_pct.toFixed(1)}%`, value: null }))} />
        </div>
      </div>
      {data.curve.length > 0 && (
        <svg
          className="reports-v2-curve"
          viewBox={`0 0 ${data.curve.length} 100`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Equity curve by closed trade"
        >
          {data.curve.map((pt, idx) => (
            <rect
              key={`${pt.trade_id ?? idx}-${pt.closed_ts}`}
              className={`reports-v2-curve-bar${books && pt.owner ? ` is-${pt.owner}` : ''}`}
              x={idx + CURVE_GAP / 2}
              width={1 - CURVE_GAP}
              y={100 - heights[idx]}
              height={heights[idx]}
            >
              <title>
                {books && pt.owner
                  ? `${pt.symbol} · ${whoName(pt.owner, pt.bot)}: ${fmtPnl(pt.equity)}`
                  : `${pt.symbol}: ${fmtPnl(pt.equity)}`}
              </title>
            </rect>
          ))}
        </svg>
      )}
      {books && <p className="reports-v2-hint">{REPORTS_DRAWDOWN_PAPER_HINT}</p>}
    </section>
  );
}
