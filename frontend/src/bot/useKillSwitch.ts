/**
 * The kill switch latch (D-037, ADR 025, ADR 042 D) for the Bots page: its status,
 * polled, and trip / reset behind the app's confirm dialog. Tripping cancels every
 * working order on every venue and blocks new buys on every venue until reset; it
 * does not sell positions. The trip's answer -- what it cancelled on each venue,
 * what it could not, and which venue it could not read -- is kept until the next
 * press, so the page can say it.
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
import {
  fetchKillSwitch,
  resetKillSwitch,
  tripKillSwitch,
  type KillSweep,
  type KillSwitchStatus,
} from './killSwitchApi';

function errorText(err: unknown): string {
  return err instanceof Error && err.message ? err.message : String(err);
}

export interface KillSwitchControl {
  status: KillSwitchStatus | null;
  error: string | null;
  busy: boolean;
  /** The last trip's sweep per venue; null before a trip in this window, or after a reset. */
  sweep: KillSweep[] | null;
  /** Trip (true) or reset (false) after the operator confirms. Resolves false when declined. */
  act: (trip: boolean) => Promise<boolean>;
}

export function useKillSwitch(): KillSwitchControl {
  const [status, setStatus] = useState<KillSwitchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sweep, setSweep] = useState<KillSweep[] | null>(null);

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
      const next = await (trip ? tripKillSwitch() : resetKillSwitch());
      setStatus(next);
      setSweep(trip ? next.sweep ?? [] : null);
      setError(null);
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  return { status, error, busy, sweep, act };
}
