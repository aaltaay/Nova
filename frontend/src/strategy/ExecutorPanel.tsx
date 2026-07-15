/**
 * Automation panel — Nova OS P4 control modes (signal | confirm).
 * auto_paper / auto_live are blocked server-side until later phases.
 * Restart always returns to signal. Kill does not remove protective stops on filled positions.
 */
import { useEffect, useState } from 'react';
import { NOVA_OS_CONFIRM_TIMEOUT_SEC, NOVA_OS_FLATTEN_CONFIRM_TOKEN, SETUP_LABELS } from '../constants';
import { useExecutor } from './useExecutor';
import type { ExecutorOpenPosition, ExecutorStagedTicket } from './types';

function fmtPrice(v: number): string {
  return `$${v.toFixed(2)}`;
}

function fmtTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

function Countdown({ expiresAt }: { expiresAt: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 500);
    return () => clearInterval(id);
  }, []);
  const left = Math.max(0, Math.ceil(expiresAt - now));
  return <span className={left <= 10 ? 'nova-os-decision-nobuy' : ''}>{left}s</span>;
}

function StagedTable({
  tickets,
  onApprove,
  onReject,
}: {
  tickets: ExecutorStagedTicket[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  if (tickets.length === 0) {
    return <div className="empty-state">No staged tickets. Raise mode to Confirm to stage BUY decisions.</div>;
  }
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Setup</th>
            <th>Entry</th>
            <th>Stop</th>
            <th>Target</th>
            <th>Shares</th>
            <th title={`Expires after ${NOVA_OS_CONFIRM_TIMEOUT_SEC}s`}>TTL</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id}>
              <td>{t.symbol}</td>
              <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[t.setup] ?? t.setup}</span></td>
              <td>{fmtPrice(t.entry)}</td>
              <td>{fmtPrice(t.stop)}</td>
              <td>{fmtPrice(t.target)}</td>
              <td>{t.shares}</td>
              <td><Countdown expiresAt={t.expires_at} /></td>
              <td className="nova-os-staged-actions">
                <button type="button" className="executor-arm-btn" onClick={() => onApprove(t.id)}>
                  Approve
                </button>
                <button type="button" className="executor-disarm-btn" onClick={() => onReject(t.id)}>
                  Reject
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpenPositionsTable({
  positions,
  onCancel,
}: {
  positions: ExecutorOpenPosition[];
  onCancel: (symbol: string) => void;
}) {
  if (positions.length === 0) {
    return <div className="empty-state">No open automated positions right now.</div>;
  }
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Opened</th>
            <th>Symbol</th>
            <th>Setup</th>
            <th>Qty</th>
            <th>Entry</th>
            <th>Stop</th>
            <th>Target</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.symbol}>
              <td className="hod-time-cell">{fmtTime(p.opened_ts)}</td>
              <td>{p.symbol}</td>
              <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[p.setup] ?? p.setup}</span></td>
              <td>{p.qty}</td>
              <td>{fmtPrice(p.entry_price)}</td>
              <td>{fmtPrice(p.stop_price)}</td>
              <td>{fmtPrice(p.target_price)}</td>
              <td>
                <button
                  type="button"
                  className="executor-disarm-btn"
                  title="Cancel only if the entry parent is still unfilled. Does not remove a protective stop on a filled position."
                  onClick={() => onCancel(p.symbol)}
                >
                  Cancel entry
                </button>
              </td>
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
  const {
    status, loading, error, actionError,
    arm, disarm, setMode, killSwitch, resetKillSwitch,
    approveStaged, rejectStaged, cancelWorkingEntry, flatten,
  } = useExecutor(active);

  const mode = status?.effective_mode ?? status?.control_mode ?? 'signal';

  const handleConfirmMode = () => {
    if (!status) return;
    const ok = window.confirm(
      `${status.disclosure}\n\nRaise to Confirm? BUY decisions will stage paper tickets for your Approve (TTL ${NOVA_OS_CONFIRM_TIMEOUT_SEC}s). Nothing places until you approve.`,
    );
    if (ok) arm();
  };

  const handleKill = () => {
    const ok = window.confirm(
      'Stop Automation: force Signal, reject staged tickets, cancel only unfilled entry parents. Protective stops on filled positions are kept. Continue?',
    );
    if (ok) killSwitch();
  };

  const handleFlatten = () => {
    const typed = window.prompt(
      `Flatten automated positions requires typing ${NOVA_OS_FLATTEN_CONFIRM_TOKEN}. This submits closing sells — verify fills in IBKR.`,
    );
    if (typed === NOVA_OS_FLATTEN_CONFIRM_TOKEN) flatten();
  };

  const handleApprove = (id: string) => {
    const ticket = status?.staged?.find((t) => t.id === id);
    if (!ticket) return;
    const ok = window.confirm(
      `Place this paper bracket now: buy ${ticket.shares} ${ticket.symbol} @ ${fmtPrice(ticket.entry)}, stop ${fmtPrice(ticket.stop)}, target ${fmtPrice(ticket.target)}?`,
    );
    if (ok) approveStaged(id);
  };

  return (
    <div className="executor-panel">
      <div className="watchlist-description">
        Control mode ladder (P4): <strong>signal</strong> (display only) or <strong>confirm</strong> (stage + Approve).
        auto_paper / auto_live stay locked until later phases. Mode resets to signal on every API restart.
      </div>

      {error && <div className="empty-state">{error}</div>}
      {actionError && <div className="empty-state">{actionError}</div>}
      {loading && !status && <div className="empty-state">Loading automation status…</div>}

      {status && (
        <>
          <div className="nova-os-mode-bar">
            <span>
              Mode: <strong className={mode === 'confirm' ? 'nova-os-decision-wait' : ''}>{mode}</strong>
              {status.loss_policy_reason && (
                <span className="na-muted"> · {status.loss_policy_reason}</span>
              )}
            </span>
            <span className="na-muted">
              IBKR {status.ibkr_connected ? status.ibkr_mode : 'disconnected'}
              {status.kill_switch_tripped ? ' · kill tripped' : ''}
            </span>
          </div>

          <div className="executor-controls">
            <button type="button" className="executor-arm-btn" disabled={mode === 'confirm'} onClick={handleConfirmMode}>
              Raise to Confirm
            </button>
            <button type="button" className="executor-disarm-btn" disabled={mode === 'signal'} onClick={() => { disarm(); void setMode('signal'); }}>
              Drop to Signal
            </button>
            <button type="button" className="executor-kill-btn" onClick={handleKill}>
              Stop Automation
            </button>
            {status.kill_switch_tripped && (
              <button type="button" className="executor-disarm-btn" onClick={() => resetKillSwitch()}>
                Reset kill
              </button>
            )}
            <button type="button" className="executor-kill-btn" onClick={handleFlatten}>
              Flatten…
            </button>
          </div>

          <p className="nova-os-disclosure">{status.disclosure}</p>

          <h4 className="nova-os-section-title">Staged queue</h4>
          <StagedTable
            tickets={status.staged ?? []}
            onApprove={handleApprove}
            onReject={(id) => rejectStaged(id)}
          />

          <h4 className="nova-os-section-title">Open positions</h4>
          <OpenPositionsTable
            positions={status.open_positions}
            onCancel={(symbol) => cancelWorkingEntry(symbol)}
          />
        </>
      )}
    </div>
  );
}
