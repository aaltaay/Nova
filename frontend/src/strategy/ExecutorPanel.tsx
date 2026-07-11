/** Automation panel — the ONLY place in the app that can turn on automated order
 * placement (backend/strategy/executor.py). Disarmed by default and on every
 * backend restart. Arming requires an explicit confirmation dialog that restates
 * the plain-language disclosure, so nothing here can be armed by an accidental
 * click, and the user always sees exactly what they are turning on. */
import { SETUP_LABELS } from '../constants';
import { useExecutor } from './useExecutor';
import type { ExecutorOpenPosition } from './types';

function fmtPrice(v: number): string {
  return `$${v.toFixed(2)}`;
}

function fmtTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

function OpenPositionsTable({ positions }: { positions: ExecutorOpenPosition[] }) {
  if (positions.length === 0) {
    return <div className="empty-state">No open automated positions right now.</div>;
  }
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th title="When this bracket order was placed.">Opened</th>
            <th title="Ticker symbol.">Symbol</th>
            <th title="Which setup pattern triggered this entry.">Setup</th>
            <th title="Share quantity from risk.position_size_shares().">Qty</th>
            <th title="Entry limit price sent to IBKR.">Entry</th>
            <th title="Stop-loss price — the max this position can lose per share.">Stop</th>
            <th title="Profit-target limit price.">Target</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => (
            <tr key={p.symbol}>
              <td className="hod-time-cell">{fmtTime(p.opened_ts)}</td>
              <td>{p.symbol}</td>
              <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[p.setup] ?? p.setup}</span></td>
              <td>{p.qty}</td>
              <td>{fmtPrice(p.entry_price)}</td>
              <td>{fmtPrice(p.stop_price)}</td>
              <td>{fmtPrice(p.target_price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface ExecutorPanelProps {
  active: boolean;
}

export function ExecutorPanel({ active }: ExecutorPanelProps) {
  const { status, loading, error, actionError, arm, disarm, killSwitch, resetKillSwitch } = useExecutor(active);

  const handleArm = () => {
    if (!status) return;
    const confirmed = window.confirm(
      `${status.disclosure}\n\nAre you sure you want to arm automation now?`
    );
    if (confirmed) arm();
  };

  const handleKillSwitch = () => {
    const confirmed = window.confirm(
      'Kill switch: this immediately disarms automation and cancels every bracket order ' +
      'it has placed. It does NOT close a position that has already filled — you decide ' +
      'that separately. Continue?'
    );
    if (confirmed) killSwitch();
  };

  return (
    <div className="journal-panel">
      <div className="watchlist-description">
        Automation is OFF by default and resets to OFF every time the backend restarts. Read the
        disclosure below before arming — it explains exactly what will happen.
      </div>

      {error && <div className="empty-state">{error}</div>}
      {!error && loading && !status && <div className="empty-state">{'Loading automation status\u2026'}</div>}

      {status && (
        <>
          <div
            className={`executor-status-card ${status.armed ? 'executor-armed' : 'executor-disarmed'}`}
            title="Live state from backend/strategy/executor.py."
          >
            <div className="executor-status-headline">
              {status.kill_switch_tripped
                ? 'KILL SWITCH TRIPPED'
                : status.armed
                  ? 'ARMED — placing paper bracket orders on approved signals'
                  : 'DISARMED — signals are display-only'}
            </div>
            <div className="executor-disclosure">{status.disclosure}</div>
            <div
              className="journal-metric"
              title="Whether the backend currently has a live connection to IB Gateway/TWS, and whether that connection is the paper or live account."
            >
              <span className="journal-metric-label">IBKR connection</span>
              <span className={status.ibkr_connected ? 'positive' : 'negative'}>
                {status.ibkr_connected ? `Connected (${status.ibkr_mode})` : 'Not connected'}
              </span>
            </div>

            {actionError && <div className="journal-halt-reason">{actionError}</div>}

            <div className="executor-actions">
              {!status.armed && !status.kill_switch_tripped && (
                <button
                  className="executor-arm-btn"
                  onClick={handleArm}
                  title="Confirms the disclosure above, then arms automation."
                >
                  Arm Automation
                </button>
              )}
              {status.armed && (
                <button
                  className="executor-disarm-btn"
                  onClick={() => disarm()}
                  title="Stops placing new bracket orders. Existing open positions are left alone."
                >
                  Disarm
                </button>
              )}
              <button
                className="executor-kill-btn"
                onClick={handleKillSwitch}
                title="Immediately disarms and cancels every bracket order this module has open."
              >
                Kill Switch
              </button>
              {status.kill_switch_tripped && (
                <button
                  className="executor-disarm-btn"
                  onClick={() => resetKillSwitch()}
                  title="Clears the tripped flag. Does not re-arm automation — use Arm Automation again."
                >
                  Reset Kill Switch
                </button>
              )}
            </div>
          </div>

          <h3
            className="journal-section-heading"
            title="Positions this module has an open bracket order for right now."
          >
            Open automated positions
          </h3>
          <OpenPositionsTable positions={status.open_positions} />
        </>
      )}
    </div>
  );
}
