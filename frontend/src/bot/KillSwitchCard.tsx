/**
 * The kill switch on the Bots page (D-037, ADR 025). It was on the retired
 * Watchlist > Automation tab; the latch itself is unchanged and still blocks
 * every new order from every source until it is reset here.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  KILL_SWITCH_CLEAR,
  KILL_SWITCH_HINT,
  KILL_SWITCH_POLL_MS,
  KILL_SWITCH_RESET_CONFIRM,
  KILL_SWITCH_RESET_LABEL,
  KILL_SWITCH_TITLE,
  KILL_SWITCH_TRIP_CONFIRM,
  KILL_SWITCH_TRIP_LABEL,
  KILL_SWITCH_TRIPPED,
  KILL_SWITCH_UNKNOWN,
} from '../constantGroups/bot';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { confirmApp } from '../ux/appDialogApi';
import {
  fetchKillSwitch,
  resetKillSwitch,
  tripKillSwitch,
  type KillSwitchStatus,
} from './killSwitchApi';

function errorText(err: unknown): string {
  return err instanceof Error && err.message ? err.message : String(err);
}

export function KillSwitchCard() {
  const [status, setStatus] = useState<KillSwitchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await fetchKillSwitch());
      setError(null);
    } catch (err) {
      setError(errorText(err));
    }
  }, []);

  useEffect(() => {
    if (onSampleDesk()) return undefined;
    void refresh();
    const id = window.setInterval(() => void refresh(), KILL_SWITCH_POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const act = useCallback(async (trip: boolean) => {
    const ok = await confirmApp({
      title: KILL_SWITCH_TITLE,
      message: trip ? KILL_SWITCH_TRIP_CONFIRM : KILL_SWITCH_RESET_CONFIRM,
      confirmLabel: trip ? KILL_SWITCH_TRIP_LABEL : KILL_SWITCH_RESET_LABEL,
      tone: trip ? 'danger' : 'warning',
    });
    if (!ok) return;
    setBusy(true);
    try {
      setStatus(await (trip ? tripKillSwitch() : resetKillSwitch()));
      setError(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const tripped = status?.tripped === true;
  const label = status == null ? KILL_SWITCH_UNKNOWN : tripped ? KILL_SWITCH_TRIPPED : KILL_SWITCH_CLEAR;

  return (
    <section
      className={`bot-strategy__card${tripped ? ' bot-strategy__card--killed' : ''}`}
      data-testid="bot-kill-switch"
    >
      <h3>{KILL_SWITCH_TITLE}</h3>
      <p className="form-hint">{KILL_SWITCH_HINT}</p>
      <p data-testid="bot-kill-switch-state" role="status">
        <strong>{label}</strong>
      </p>
      {error ? <p className="form-hint" data-testid="bot-kill-switch-error">{error}</p> : null}
      <div className="bot-strategy__row-actions">
        {tripped ? (
          <button type="button" disabled={busy} onClick={() => void act(false)}>
            {KILL_SWITCH_RESET_LABEL}
          </button>
        ) : (
          <button
            type="button"
            className="bot-strategy__danger"
            disabled={busy || status == null}
            onClick={() => void act(true)}
          >
            {KILL_SWITCH_TRIP_LABEL}
          </button>
        )}
      </div>
    </section>
  );
}
