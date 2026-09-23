/**
 * The kill switch latch (D-037, ADR 025) for the Bots page: its status, polled,
 * and trip / reset behind the app's confirm dialog. The latch refuses every new
 * order from every source until it is reset; flatten and cancel still work.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  KILL_SWITCH_POLL_MS,
  KILL_SWITCH_RESET_CONFIRM,
  KILL_SWITCH_RESET_LABEL,
  KILL_SWITCH_TITLE,
  KILL_SWITCH_TRIP_CONFIRM,
  KILL_SWITCH_TRIP_LABEL,
} from '../constantGroups/bot';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { confirmApp } from '../ux/appDialogApi';
import { fetchKillSwitch, resetKillSwitch, tripKillSwitch, type KillSwitchStatus } from './killSwitchApi';

function errorText(err: unknown): string {
  return err instanceof Error && err.message ? err.message : String(err);
}

export interface KillSwitchControl {
  status: KillSwitchStatus | null;
  error: string | null;
  busy: boolean;
  /** Trip (true) or reset (false) after the operator confirms. Resolves false when declined. */
  act: (trip: boolean) => Promise<boolean>;
}

export function useKillSwitch(): KillSwitchControl {
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
    if (!ok) return false;
    setBusy(true);
    try {
      setStatus(await (trip ? tripKillSwitch() : resetKillSwitch()));
      setError(null);
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  return { status, error, busy, act };
}
