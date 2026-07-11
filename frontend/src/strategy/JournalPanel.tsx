/** Journal panel — go/no-go live-money gate + trade metrics + recent detected signals.
 * Read-only. No control here places, modifies, or cancels an order. */
import { SETUP_LABELS } from '../constants';
import type { GoNoGoCriterion, JournalMetrics, JournalSignalRow } from './types';

function fmtTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

function fmtPrice(v: number | null): string {
  return v == null ? '\u2014' : `$${v.toFixed(2)}`;
}

function fmtPct(v: number | null): string {
  return v == null ? '\u2014' : `${v.toFixed(1)}%`;
}

function fmtRatio(v: number | null): string {
  return v == null ? '\u2014' : `${v.toFixed(2)}:1`;
}

function CriterionRow({ criterion }: { criterion: GoNoGoCriterion }) {
  const status = criterion.met === null ? 'pending' : criterion.met ? 'pass' : 'fail';
  const icon = status === 'pending' ? '\u2026' : status === 'pass' ? '\u2713' : '\u2717';
  return (
    <li className={`go-no-go-criterion go-no-go-${status}`}>
      <span className="go-no-go-icon">{icon}</span> {criterion.label}
    </li>
  );
}

function GoNoGoBar({ metrics }: { metrics: JournalMetrics }) {
  const { go_no_go: gng } = metrics;
  return (
    <div className={`go-no-go-bar ${gng.overall_go ? 'go-no-go-go' : 'go-no-go-nogo'}`}>
      <div className="go-no-go-headline">
        {gng.overall_go ? 'GO — live-money bar cleared' : 'NO-GO — stay in paper'}
      </div>
      <ul className="go-no-go-list">
        <CriterionRow criterion={gng.criteria.min_sample_size} />
        <CriterionRow criterion={gng.criteria.profit_loss_ratio} />
        <CriterionRow criterion={gng.criteria.adherence} />
      </ul>
    </div>
  );
}

function MetricsSummary({ metrics }: { metrics: JournalMetrics }) {
  return (
    <div className="journal-metrics-grid">
      <div className="journal-metric"><span className="journal-metric-label">Closed trades</span><span>{metrics.total_closed_trades}</span></div>
      <div className="journal-metric"><span className="journal-metric-label">Win rate</span><span>{fmtPct(metrics.win_rate_pct)}</span></div>
      <div className="journal-metric"><span className="journal-metric-label">Avg win</span><span>{fmtPrice(metrics.avg_win_dollars)}</span></div>
      <div className="journal-metric"><span className="journal-metric-label">Avg loss</span><span>{fmtPrice(metrics.avg_loss_dollars)}</span></div>
      <div className="journal-metric"><span className="journal-metric-label">P/L ratio</span><span>{fmtRatio(metrics.profit_loss_ratio)}</span></div>
      <div className="journal-metric"><span className="journal-metric-label">Total P&amp;L</span><span>{fmtPrice(metrics.total_pnl_dollars)}</span></div>
      <div className="journal-metric"><span className="journal-metric-label">Adherence</span><span>{fmtPct(metrics.adherence_pct)}</span></div>
    </div>
  );
}

interface JournalPanelProps {
  metrics: JournalMetrics | null;
  signals: JournalSignalRow[];
  loading: boolean;
  error: string | null;
}

export function JournalPanel({ metrics, signals, loading, error }: JournalPanelProps) {
  return (
    <div className="journal-panel">
      <div className="watchlist-description">
        Every detected setup is logged here automatically. Trade metrics stay empty until paper
        execution (Phase D) starts closing trades — no order-placing code exists yet, so this is
        signal-only.
      </div>
      {error && <div className="empty-state">{error}</div>}
      {!error && loading && !metrics && <div className="empty-state">Loading journal\u2026</div>}
      {metrics && (
        <>
          <GoNoGoBar metrics={metrics} />
          <MetricsSummary metrics={metrics} />
        </>
      )}

      <h3 className="journal-section-heading">Recent detected signals</h3>
      {signals.length === 0 ? (
        <div className="empty-state">No signals logged yet.</div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Setup</th>
                <th>Entry</th>
                <th>Stop</th>
                <th>Target</th>
              </tr>
            </thead>
            <tbody>
              {signals.map(s => (
                <tr key={s.id}>
                  <td className="hod-time-cell">{fmtTime(s.ts)}</td>
                  <td>{s.symbol}</td>
                  <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[s.setup] ?? s.setup}</span></td>
                  <td>{fmtPrice(s.entry_price)}</td>
                  <td>{fmtPrice(s.stop_price)}</td>
                  <td>{fmtPrice(s.target_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
