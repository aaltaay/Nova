/** Compact arm / disarm / kill controls for the ticker trading action bar.
 * Same safety dialogs as ExecutorPanel — reuses useExecutor. */
import { useExecutor } from '../strategy/useExecutor';

interface Props {
  enabled: boolean;
}

export function TickerTradeAutomateControls({ enabled }: Props) {
  const { status, actionError, arm, disarm, killSwitch, resetKillSwitch } = useExecutor(enabled);

  function handleArm() {
    if (!status) return;
    const confirmed = window.confirm(`${status.disclosure}\n\nArm automation now?`);
    if (confirmed) arm();
  }

  function handleKill() {
    const confirmed = window.confirm(
      'Kill switch: immediately disarms automation and cancels every bracket order it placed. ' +
        'It does NOT flatten a filled position — use Close for that. Continue?',
    );
    if (confirmed) killSwitch();
  }

  return (
    <div className="ticker-trade-bar-automate">
      <span className="ticker-trade-bar-group-label">Automate</span>
      {status?.kill_switch_tripped ? (
        <button type="button" className="executor-disarm-btn" onClick={() => resetKillSwitch()}>
          Reset Kill
        </button>
      ) : status?.armed ? (
        <button type="button" className="executor-disarm-btn" onClick={() => disarm()}>
          Disarm
        </button>
      ) : (
        <button
          type="button"
          className="executor-arm-btn"
          onClick={handleArm}
          disabled={!status}
          title={status?.disclosure}
        >
          Arm
        </button>
      )}
      <button type="button" className="executor-kill-btn" onClick={handleKill}>
        Kill
      </button>
      {status && (
        <span
          className={`ticker-trade-auto-state${status.armed ? ' armed' : ''}`}
          title={status.disclosure}
        >
          {status.kill_switch_tripped ? 'KILL TRIPPED' : status.armed ? 'ARMED' : 'DISARMED'}
        </span>
      )}
      {actionError && <span className="ticker-trade-bar-disabled-why">{actionError}</span>}
    </div>
  );
}
