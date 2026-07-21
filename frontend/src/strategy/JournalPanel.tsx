/** Journal panel — go/no-go live-money gate + trade metrics + today's risk state
 * + recent detected signals/trades. Read-only. No control here places, modifies,
 * or cancels an order. The "Show demo data" toggle is the ONLY control that
 * changes what data is displayed, and it is off by default and clearly banner'd
 * when on — nothing here silently substitutes fake data for real. */
import { useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SETUP_LABELS } from '../constants';
import { formatShareQty } from '../utils/formatShareQty';
import { useJournal } from './useJournal';
import type { GoNoGoCriterion, JournalMetrics, JournalTradeRow, RiskStatus } from './types';

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
  const statusText = status === 'pending' ? 'not enough data yet' : status === 'pass' ? 'met' : 'not met';
  return (
    <li
      className={`go-no-go-criterion go-no-go-${status}`}
      title={`${criterion.label} — currently ${statusText}${criterion.value == null ? '' : ` (current value: ${criterion.value})`}.`}
    >
      <span className="go-no-go-icon">{icon}</span> {criterion.label}
    </li>
  );
}

function GoNoGoBar({ metrics }: { metrics: JournalMetrics }) {
  const { go_no_go: gng } = metrics;
  return (
    <div
      className={`go-no-go-bar ${gng.overall_go ? 'go-no-go-go' : 'go-no-go-nogo'}`}
      title="Live-money gate: all three criteria must pass before auto_live or real-money execution is considered. Paper brackets can run when the executor is armed and IBKR spend is unlocked; this bar gates live money only."
    >
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
      <div className="journal-metric" title="Number of trades with a recorded profit/loss. Open (unclosed) trades are not counted.">
        <span className="journal-metric-label">Closed trades</span><span>{metrics.total_closed_trades}</span>
      </div>
      <div className="journal-metric" title="Percent of closed trades with a positive P&L.">
        <span className="journal-metric-label">Win rate</span><span>{fmtPct(metrics.win_rate_pct)}</span>
      </div>
      <div className="journal-metric" title="Average dollar profit across only the winning trades.">
        <span className="journal-metric-label">Avg win</span><span>{fmtPrice(metrics.avg_win_dollars)}</span>
      </div>
      <div className="journal-metric" title="Average dollar loss across only the losing trades (shown as a positive number).">
        <span className="journal-metric-label">Avg loss</span><span>{fmtPrice(metrics.avg_loss_dollars)}</span>
      </div>
      <div className="journal-metric" title="Average win divided by average loss. The course targets 2:1 or better — bigger winners than losers.">
        <span className="journal-metric-label">P/L ratio</span><span>{fmtRatio(metrics.profit_loss_ratio)}</span>
      </div>
      <div className="journal-metric" title="Sum of every closed trade's P&L.">
        <span className="journal-metric-label">Total P&amp;L</span><span>{fmtPrice(metrics.total_pnl_dollars)}</span>
      </div>
      <div className="journal-metric" title="Percent of trades flagged 'adherent' — followed the risk rules (correct size, respected the stop, didn't trade through a halt). Must be 100% to pass the go/no-go bar.">
        <span className="journal-metric-label">Adherence</span><span>{fmtPct(metrics.adherence_pct)}</span>
      </div>
    </div>
  );
}

function RiskCard({ risk }: { risk: RiskStatus }) {
  return (
    <div
      className="journal-risk-card"
      title="Live state from backend/strategy/risk.py — real, not demo data. Updates when the executor records closed bracket fills via record_trade_result(); reads all-zero until paper trades close."
    >
      <div className="journal-section-heading" title="This is the current real discipline state for today's session — resets automatically at 4 AM ET.">
        Today&apos;s risk state (real, resets daily at 4 AM ET)
      </div>
      <div className="journal-metrics-grid">
        <div className="journal-metric" title="Whether the risk engine will currently allow a new trade. Turns 'Halted' if any walk-away guardrail trips (daily max loss, 3 losses in a row, or giving back half of today's peak profit) and stays that way until the next session reset.">
          <span className="journal-metric-label">Status</span>
          <span className={risk.can_trade ? 'positive' : 'negative'}>{risk.can_trade ? 'Can trade' : 'Halted'}</span>
        </div>
        <div className="journal-metric" title="Today's realized profit/loss across all closed trades so far.">
          <span className="journal-metric-label">Daily P&amp;L</span><span>{fmtPrice(risk.daily_realized_pnl)}</span>
        </div>
        <div className="journal-metric" title="The highest daily P&L reached today. Giving back half of this triggers a walk-away halt.">
          <span className="journal-metric-label">Peak P&amp;L</span><span>{fmtPrice(risk.peak_daily_pnl)}</span>
        </div>
        <div className="journal-metric" title="Current losing streak. 3 in a row triggers a walk-away halt for the day.">
          <span className="journal-metric-label">Loss streak</span><span>{risk.consecutive_losses}</span>
        </div>
        <div className="journal-metric" title="Number of trades closed so far in today's session.">
          <span className="journal-metric-label">Trades today</span><span>{risk.trades_today}</span>
        </div>
        <div className="journal-metric" title="Share size the risk engine would currently size the next trade at — quarter size until a profit cushion is reached, cut after a meaningful loss.">
          <span className="journal-metric-label">Next size</span><span>{risk.position_size_shares} sh</span>
        </div>
      </div>
      {!risk.can_trade && risk.halt_reason && (
        <div className="journal-halt-reason" title="The specific guardrail that halted trading for the rest of today's session.">
          {risk.halt_reason}
        </div>
      )}
    </div>
  );
}

function TradesTable({
  trades,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: {
  trades: JournalTradeRow[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  if (trades.length === 0) {
    return <div className="empty-state">No closed trades yet — this table populates when the executor closes paper bracket fills and journals them.</div>;
  }
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th title="When the trade closed.">Closed</th>
            <th title="Ticker symbol. Click: Quote Panel · Double-click: Trader.">Symbol</th>
            <th title="Which setup pattern triggered the entry.">Setup</th>
            <th title="Long (bought first) or short (sold first).">Side</th>
            <th title="Share quantity.">Qty</th>
            <th title="Fill price at entry.">Entry</th>
            <th title="Fill price at exit.">Exit</th>
            <th title="Realized profit or loss on this trade in dollars.">P&amp;L</th>
            <th title="Whether this trade followed the risk rules exactly (correct size, respected the stop, no trading through a halt).">Adherent</th>
          </tr>
        </thead>
        <tbody>
          {trades.map(t => (
            <SelectableTableRow
              key={t.id}
              symbol={t.symbol}
              selected={selectedSymbol === t.symbol}
              onSelect={onSelectSymbol}
              onOpenTrading={onOpenTrading}
              className={t.is_mock ? 'row-mock' : ''}
            >
              <td className="hod-time-cell">{t.closed_ts ? fmtTime(t.closed_ts) : '\u2014'}</td>
              <td>{t.symbol}{t.is_mock ? <span className="mock-tag" title="Synthetic demo row — not a real trade.">DEMO</span> : null}</td>
              <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[t.setup ?? ''] ?? t.setup ?? '\u2014'}</span></td>
              <td>{t.side}</td>
              <td>{formatShareQty(t.qty)}</td>
              <td>{fmtPrice(t.entry_price)}</td>
              <td>{fmtPrice(t.exit_price)}</td>
              <td className={t.pnl != null && t.pnl >= 0 ? 'positive' : 'negative'}>{fmtPrice(t.pnl)}</td>
              <td>{t.adherent == null ? '\u2014' : t.adherent ? '\u2713' : '\u2717'}</td>
            </SelectableTableRow>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface JournalPanelProps {
  active: boolean;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function JournalPanel({
  active,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: JournalPanelProps) {
  const [includeMock, setIncludeMock] = useState(false);
  const { metrics, signals, trades, risk, loading, error } = useJournal(active, includeMock);

  return (
    <div className="journal-panel">
      <div className="watchlist-description">
        Every detected setup is logged here automatically. Trade metrics populate when the IBKR
        executor closes paper bracket fills; signals are always recorded even when automation is
        disarmed.
      </div>

      <label
        className="journal-demo-toggle"
        title="Loads a fixed set of 12 hand-written synthetic trades (tagged 'DEMO', never counted in real results) so you can see exactly how the metrics and go/no-go bar behave once real trades start flowing in. Turn off to see only real data. Real users never see demo rows unless this box is checked."
      >
        <input type="checkbox" checked={includeMock} onChange={e => setIncludeMock(e.target.checked)} />
        Show demo data (synthetic test trades — not real)
      </label>

      {includeMock && (
        <div className="journal-demo-banner">
          DEMO DATA ACTIVE — the trades and metrics below include 12 synthetic test rows tagged
          "DEMO", not real trades. Uncheck "Show demo data" above to see only real results.
        </div>
      )}

      {error && <div className="empty-state">{error}</div>}
      {!error && loading && !metrics && <div className="empty-state">{'Loading journal\u2026'}</div>}
      {metrics && (
        <>
          <GoNoGoBar metrics={metrics} />
          <MetricsSummary metrics={metrics} />
        </>
      )}

      {risk && <RiskCard risk={risk} />}

      <h3 className="journal-section-heading" title="Closed trades from executor paper fills, plus demo rows only when the toggle above is checked.">
        Trades
      </h3>
      <TradesTable
        trades={trades}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={onSelectSymbol}
        onOpenTrading={onOpenTrading}
      />

      <h3 className="journal-section-heading" title="Every setup the scanner flagged as eligible, in real time — this table is always real data, the demo toggle above does not affect it.">
        Recent detected signals
      </h3>
      {signals.length === 0 ? (
        <div className="empty-state">No signals logged yet.</div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th title="Click: Quote Panel · Double-click: Trader">Symbol</th>
                <th>Setup</th>
                <th>Entry</th>
                <th>Stop</th>
                <th>Target</th>
              </tr>
            </thead>
            <tbody>
              {signals.map(s => (
                <SelectableTableRow
                  key={s.id}
                  symbol={s.symbol}
                  selected={selectedSymbol === s.symbol}
                  onSelect={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                >
                  <td className="hod-time-cell">{fmtTime(s.ts)}</td>
                  <td>{s.symbol}</td>
                  <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[s.setup] ?? s.setup}</span></td>
                  <td>{fmtPrice(s.entry_price)}</td>
                  <td>{fmtPrice(s.stop_price)}</td>
                  <td>{fmtPrice(s.target_price)}</td>
                </SelectableTableRow>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
