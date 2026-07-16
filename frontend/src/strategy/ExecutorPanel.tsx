/**
 * Automation panel — Nova OS P5 control modes (signal | confirm | auto_paper).
 * auto_live stays blocked. Restart always returns to signal.
 * Kill does not remove protective stops on filled positions.
 */
import { NOVA_OS_CONFIRM_TIMEOUT_SEC, NOVA_OS_FLATTEN_CONFIRM_TOKEN } from '../constants';
import { OpenPositionsTable, StagedTable, fmtPrice } from './ExecutorTables';
import { useExecutor } from './useExecutor';

interface ExecutorPanelProps {
  active: boolean;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function ExecutorPanel({
  active,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: ExecutorPanelProps) {
  const {
    status, loading, error, actionError,
    arm, disarm, setMode, killSwitch, resetKillSwitch,
    approveStaged, rejectStaged, cancelWorkingEntry, flatten,
  } = useExecutor(active);

  const mode = status?.effective_mode ?? status?.control_mode ?? 'signal';
  const paperGateway = Boolean(status?.ibkr_connected && status?.ibkr_mode === 'paper');
  const autoPaperActive = mode === 'auto_paper';

  const handleConfirmMode = () => {
    if (!status) return;
    const ok = window.confirm(
      `${status.disclosure}\n\nRaise to Confirm? BUY decisions will stage paper tickets for your Approve (TTL ${NOVA_OS_CONFIRM_TIMEOUT_SEC}s). Nothing places until you approve.`,
    );
    if (ok) arm();
  };

  const handleAutoPaper = () => {
    if (!status || !paperGateway) return;
    const ok = window.confirm(
      `${status.disclosure}\n\nRaise to Auto Paper?\n\nBUY decisions will PLACE paper brackets automatically — no Approve step. Only available on paper Gateway with orders enabled.`,
    );
    if (ok) void setMode('auto_paper');
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
        Control mode ladder (P5): <strong>signal</strong> (display), <strong>confirm</strong> (stage + Approve),
        or <strong>auto_paper</strong> (places without Approve on paper Gateway).
        auto_live stays locked. Mode resets to signal on every API restart.
      </div>

      {error && <div className="empty-state">{error}</div>}
      {actionError && <div className="empty-state">{actionError}</div>}
      {loading && !status && <div className="empty-state">Loading automation status…</div>}

      {status && (
        <>
          <div className="nova-os-mode-bar">
            <span>
              Mode:{' '}
              <strong className={mode === 'confirm' || autoPaperActive ? 'nova-os-decision-wait' : ''}>
                {mode}
              </strong>
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
            <button
              type="button"
              className="executor-arm-btn"
              disabled={!paperGateway || autoPaperActive}
              title={
                paperGateway
                  ? 'Places paper brackets automatically — no Approve'
                  : 'Requires IBKR connected on paper Gateway'
              }
              onClick={handleAutoPaper}
            >
              Raise to Auto Paper
            </button>
            <button
              type="button"
              className="executor-disarm-btn"
              disabled
              title="auto_live is not enabled — live money stays blocked"
            >
              Auto Live (blocked)
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

          {autoPaperActive && (
            <p className="nova-os-disclosure nova-os-decision-wait">
              Auto Paper is on: BUY decisions place paper brackets without Approve. Drop to Signal or Confirm to stop auto placement.
            </p>
          )}

          <p className="nova-os-disclosure">{status.disclosure}</p>

          <h4 className="nova-os-section-title">Staged queue</h4>
          <StagedTable
            tickets={status.staged ?? []}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={onSelectSymbol}
            onOpenTrading={onOpenTrading}
            onApprove={handleApprove}
            onReject={(id) => rejectStaged(id)}
          />

          <h4 className="nova-os-section-title">Open positions</h4>
          <OpenPositionsTable
            positions={status.open_positions}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={onSelectSymbol}
            onOpenTrading={onOpenTrading}
            onCancel={(symbol) => cancelWorkingEntry(symbol)}
          />
        </>
      )}
    </div>
  );
}
