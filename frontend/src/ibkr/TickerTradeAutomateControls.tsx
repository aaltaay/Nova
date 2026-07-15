/** Compact control-mode ladder for the ticker trading action bar.
 * Mirrors ExecutorPanel's signal/confirm/auto_paper vocabulary and confirm
 * dialogs exactly — this bar must never show a binary "armed" state that
 * hides whether BUY decisions would stage for Approve (confirm) or place
 * without one (auto_paper). Reuses useExecutor for the same status/actions. */
import { NOVA_OS_CONFIRM_TIMEOUT_SEC } from '../constants';
import { useExecutor } from '../strategy/useExecutor';

interface Props {
  enabled: boolean;
}

export function TickerTradeAutomateControls({ enabled }: Props) {
  const { status, actionError, setMode, disarm, killSwitch, resetKillSwitch } =
    useExecutor(enabled);

  const mode = status?.effective_mode ?? status?.control_mode ?? 'signal';
  const paperGateway = Boolean(status?.ibkr_connected && status?.ibkr_mode === 'paper');

  function handleConfirmMode() {
    if (!status) return;
    const confirmed = window.confirm(
      `${status.disclosure}\n\nRaise to Confirm? BUY decisions will stage paper tickets for your Approve (TTL ${NOVA_OS_CONFIRM_TIMEOUT_SEC}s). Nothing places until you approve.`,
    );
    if (confirmed) void setMode('confirm');
  }

  function handleAutoPaper() {
    if (!status || !paperGateway) return;
    const confirmed = window.confirm(
      `${status.disclosure}\n\nRaise to Auto Paper?\n\nBUY decisions will PLACE paper brackets automatically — no Approve step. Only available on paper Gateway with orders enabled.`,
    );
    if (confirmed) void setMode('auto_paper');
  }

  function handleKill() {
    const confirmed = window.confirm(
      'Stop Automation: force Signal, reject staged tickets, cancel only unfilled entry parents. ' +
        'Protective stops on filled positions are kept — use Close for that. Continue?',
    );
    if (confirmed) killSwitch();
  }

  return (
    <div className="ticker-trade-bar-automate">
      <span className="ticker-trade-bar-group-label">Automate</span>
      {status && (
        <span
          className={`ticker-trade-auto-state${mode !== 'signal' ? ' armed' : ''}${mode === 'auto_paper' ? ' auto-paper' : ''}`}
          title={status.disclosure}
        >
          {status.kill_switch_tripped ? 'KILL TRIPPED' : mode.toUpperCase()}
        </span>
      )}
      {status?.kill_switch_tripped ? (
        <button type="button" className="executor-disarm-btn" onClick={() => resetKillSwitch()}>
          Reset Kill
        </button>
      ) : (
        <>
          <button
            type="button"
            className="executor-arm-btn"
            disabled={!status || mode === 'confirm'}
            title="Stage BUY decisions for your Approve — nothing places automatically"
            onClick={handleConfirmMode}
          >
            Confirm
          </button>
          <button
            type="button"
            className="executor-arm-btn"
            disabled={!status || !paperGateway || mode === 'auto_paper'}
            title={
              paperGateway
                ? 'Places paper brackets automatically — no Approve step'
                : 'Requires IBKR connected on paper Gateway'
            }
            onClick={handleAutoPaper}
          >
            Auto Paper
          </button>
          <button
            type="button"
            className="executor-disarm-btn"
            disabled={!status || mode === 'signal'}
            onClick={() => void disarm()}
          >
            Signal
          </button>
        </>
      )}
      <button type="button" className="executor-kill-btn" onClick={handleKill}>
        Stop Automation
      </button>
      {actionError && <span className="ticker-trade-bar-disabled-why">{actionError}</span>}
    </div>
  );
}
