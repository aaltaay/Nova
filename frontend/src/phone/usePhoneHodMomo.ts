/**
 * The desk's HOD Momo feed on the phone: the live socket, or on a Sim replay the alert history at the desk's
 * playhead (the desk's own two hooks). Opened only while a screen that shows it is up: the first frame is the
 * whole day's alerts.
 *
 * It also remembers when each stock first alerted today, so Search can say "HOD Momo 07:43" beside a match
 * without opening the feed itself.
 */
import { useEffect, useMemo } from 'react';
import { hodReplayEmptyText } from '../hod_momo/hodMomoReplayCopy';
import { useHodMomoReplay } from '../hod_momo/useHodMomoReplay';
import { useHodMomoStream } from '../hod_momo/useHodMomoStream';
import { phoneHodRows, type PhoneHodRow } from './phoneHod';

let catches: ReadonlyMap<string, string> = new Map();

/** Symbol to "HH:MM" of its first HOD Momo alert today, as last read on this phone. Empty before the first read. */
export function hodCatchTimes(): ReadonlyMap<string, string> {
  return catches;
}

export interface PhoneHodMomo {
  hodMomo: PhoneHodRow[];
  runningUp: PhoneHodRow[];
  connected: boolean;
  /** Why there are no rows, in the desk's words; null while there are, or while the day simply has none yet. */
  absence: string | null;
}

export function usePhoneHodMomo(): PhoneHodMomo {
  // The phone has no ping of its own: the PC's notification is what tells it.
  const live = useHodMomoStream({ quiet: true });
  const replay = useHodMomoReplay();
  const alerts = replay ? replay.alerts : live.alerts;
  const lists = useMemo(
    () => ({ hodMomo: phoneHodRows(alerts, 'hod_momo'), runningUp: phoneHodRows(alerts, 'running_up') }),
    [alerts],
  );
  useEffect(() => {
    // A replayed day's alerts are not today's: Search speaks of today.
    if (!replay) catches = new Map(lists.hodMomo.map((r) => [r.symbol, r.at]));
  }, [lists.hodMomo, replay]);

  let absence: string | null = null;
  if (replay) absence = alerts.length ? null : hodReplayEmptyText(replay.state);
  else if (live.feedError) absence = live.feedError;
  else if (!live.connected && !alerts.length) absence = 'Connecting to the HOD Momo feed…';
  return { ...lists, connected: replay ? true : live.connected, absence };
}
