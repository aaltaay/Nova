/**
 * Automation panel — Nova OS P5 control modes (signal | confirm | auto_paper).
 * auto_live stays blocked. Restart always returns to signal.
 * Kill does not remove protective stops on filled positions.
 * Phase G: keyboard shortcuts via useHotkeys (order keys blocked in signal).
 */
import { useCallback, useState } from 'react';
import {
  APP_DIALOG_FLATTEN_LABEL,
  APP_DIALOG_KILL_LABEL,
  APP_DIALOG_PLACE_LABEL,
  NOVA_OS_CONFIRM_TIMEOUT_SEC,
  NOVA_OS_FLATTEN_CONFIRM_TOKEN,
} from '../constants';
import { useHotkeys } from '../hooks/useHotkeys';
import { confirmApp, promptApp } from '../ux';
import { OpenPositionsTable, StagedTable, fmtPrice } from './ExecutorTables';
import { HotkeySettings } from './HotkeySettings';
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

  const [hotkeyNotice, setHotkeyNotice] = useState<string | null>(null);

  const mode = status?.effective_mode ?? status?.control_mode ?? 'signal';
  const paperGateway = Boolean(status?.ibkr_connected && status?.ibkr_mode === 'paper');
  const autoPaperActive = mode === 'auto_paper';
  const firstStaged = status?.staged?.[0] ?? null;

  const handleConfirmMode = useCallback(() => {
    if (!status) return;
    void confirmApp({
      title: 'Raise to Confirm?',
      message:
        `${status.disclosure}\n\nBUY decisions will stage paper tickets for your Approve (TTL ${NOVA_OS_CONFIRM_TIMEOUT_SEC}s). Nothing places until you approve.`,
      confirmLabel: 'Raise to Confirm',
      tone: 'warning',
    }).then(ok => {
      if (ok) arm();
    });
  }, [status, arm]);

  const handleAutoPaper = () => {
    if (!status || !paperGateway) return;
    void confirmApp({
      title: 'Raise to Auto Paper?',
      message:
        `${status.disclosure}\n\nBUY decisions will PLACE paper brackets automatically — no Approve step. Only available on paper Gateway with orders enabled.`,
      confirmLabel: 'Raise to Auto Paper',
      tone: 'warning',
    }).then(ok => {
      if (ok) void setMode('auto_paper');
    });
  };

  const handleKill = useCallback(() => {
    void confirmApp({
      title: 'Stop Automation?',
      message:
        'Force Signal, reject staged tickets, cancel only unfilled entry parents. Protective stops on filled positions are kept. Continue?',
      confirmLabel: APP_DIALOG_KILL_LABEL,
      tone: 'danger',
    }).then(ok => {
      if (ok) killSwitch();
    });
  }, [killSwitch]);

  const handleFlatten = useCallback(() => {
    void promptApp({
      title: 'Flatten automated positions',
      message:
        `Type ${NOVA_OS_FLATTEN_CONFIRM_TOKEN} to confirm. This submits closing sells — verify fills in IBKR.`,
      confirmLabel: APP_DIALOG_FLATTEN_LABEL,
      expectedValue: NOVA_OS_FLATTEN_CONFIRM_TOKEN,
      placeholder: NOVA_OS_FLATTEN_CONFIRM_TOKEN,
      tone: 'danger',
    }).then(typed => {
      if (typed === NOVA_OS_FLATTEN_CONFIRM_TOKEN) flatten();
    });
  }, [flatten]);

  const handleApprove = useCallback((id: string) => {
    const ticket = status?.staged?.find((t) => t.id === id);
    if (!ticket) return;
    void confirmApp({
      title: `Place ${ticket.symbol} paper bracket?`,
      message:
        `Buy ${ticket.shares} ${ticket.symbol} @ ${fmtPrice(ticket.entry)}, stop ${fmtPrice(ticket.stop)}, target ${fmtPrice(ticket.target)}?`,
      confirmLabel: APP_DIALOG_PLACE_LABEL,
      tone: 'warning',
    }).then(ok => {
      if (ok) approveStaged(id);
    });
  }, [status?.staged, approveStaged]);

  const handleApproveFirst = useCallback(() => {
    if (!firstStaged) {
      setHotkeyNotice('No staged ticket to approve.');
      return;
    }
    handleApprove(firstStaged.id);
  }, [firstStaged, handleApprove]);

  const handleRejectFirst = useCallback(() => {
    if (!firstStaged) {
      setHotkeyNotice('No staged ticket to reject.');
      return;
    }
    rejectStaged(firstStaged.id);
  }, [firstStaged, rejectStaged]);

  useHotkeys({
    enabled: active && Boolean(status),
    mode,
    callbacks: {
      approve_staged: handleApproveFirst,
      reject_staged: handleRejectFirst,
      arm_confirm: handleConfirmMode,
      disarm_signal: () => { disarm(); void setMode('signal'); },
      focus_flatten: handleFlatten,
      kill_switch: handleKill,
    },
    onBlocked: (_action, message) => setHotkeyNotice(message),
  });

  return (
    <div className="executor-panel">
      <div className="watchlist-description">
        Control mode ladder (P5): <strong>signal</strong> (display), <strong>confirm</strong> (stage + Approve),
        or <strong>auto_paper</strong> (places without Approve on paper Gateway).
        auto_live stays locked. Mode resets to signal on every API restart.
      </div>

      {error && <div className="empty-state">{error}</div>}
      {actionError && <div className="empty-state">{actionError}</div>}
      {hotkeyNotice && <div className="empty-state">{hotkeyNotice}</div>}
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
            <button
              type="button"
              className="executor-arm-btn"
              disabled={!firstStaged || mode === 'signal'}
              title={
                mode === 'signal'
                  ? 'Raise to Confirm before placing brackets'
                  : firstStaged
                    ? `Approve staged ${firstStaged.symbol} bracket (same path as Approve button)`
                    : 'No staged ticket'
              }
              onClick={handleApproveFirst}
            >
              Place bracket…
            </button>
          </div>

          {autoPaperActive && (
            <p className="nova-os-disclosure nova-os-decision-wait">
              Auto Paper is on: BUY decisions place paper brackets without Approve. Drop to Signal or Confirm to stop auto placement.
            </p>
          )}

          <p className="nova-os-disclosure">{status.disclosure}</p>

          <HotkeySettings mode={mode} />

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
