/**
 * Desk ping when a new HOD Momo alert row arrives.
 *
 * Banner mute is a separate localStorage preference -- not `cfg.audio`.
 * `cfg.audio` is per-strategy backend config (momentum "Audio Alert" lanes)
 * and is never consumed to play a sound. A single header toggle cannot be
 * that field: defaults differ by strategy, it lives on the server, and
 * Configure would have to open to change it.
 *
 * Cue uses the same short Web Audio oscillator shape as novaOsAttention
 * (quiet sine, ~180ms). Nova OS mute is not shared -- HOD silence must
 * not mute kill/fill cues.
 *
 * Coalesce: one ping per HOD_MOMO_ALERT_SOUND_COALESCE_MS burst.
 * Running Up (strategy 12) does not ping. WS `initial` / reconnect
 * snapshots seed seen keys and never ping.
 *
 * Its switch and volume live in sound/ (the header's sound menu sets them too);
 * the header mute silences it, above this switch.
 *
 * Sim off the live edge (#486): the strip shows another moment, so a live
 * alert that arrives then is marked seen without a ping -- and, being seen,
 * never pings late once the desk is back at the live edge.
 */
import { HOD_MOMO_ALERT_SOUND_COALESCE_MS } from './hodMomoAlertSoundConstants';
import { isRunningUpStrategy } from './scannerPartition';
import type { AlertObject } from './types';
import {
  DESK_TONE_HOD,
  deskSoundAudible,
  deskSoundOn,
  playDeskTone,
  resetDeskSoundsForTests,
  resetDeskTonesForTests,
  setDeskSoundOn,
  subscribeDeskSounds,
  unlockDeskTones,
} from '../sound';

export type HodMomoPingReason =
  | 'pinged'
  | 'coalesced'
  | 'muted'
  | 'duplicate'
  | 'running_up'
  | 'replaying';

type Listener = (enabled: boolean) => void;

const seenKeys = new Set<string>();
let lastPingAt = 0;

export function hodMomoAlertDedupeKey(
  alert: Pick<AlertObject, 'id' | 'ticker' | 'timestamp'>,
): string {
  const id = typeof alert.id === 'string' ? alert.id.trim() : '';
  if (id) return `id:${id}`;
  const ticker = String(alert.ticker ?? '').trim().toUpperCase();
  return `sym:${ticker}|${alert.timestamp ?? ''}`;
}

export function isHodMomoAlertSoundEnabled(): boolean {
  return deskSoundOn('hod');
}

export function setHodMomoAlertSoundEnabled(next: boolean): void {
  setDeskSoundOn('hod', next);
  if (next) unlockDeskTones();
}

export function subscribeHodMomoAlertSound(listener: Listener): () => void {
  listener(deskSoundOn('hod'));
  return subscribeDeskSounds(() => listener(deskSoundOn('hod')));
}

export function rememberHodMomoAlertSnapshot(alerts: readonly AlertObject[]): void {
  seenKeys.clear();
  for (const alert of alerts) {
    seenKeys.add(hodMomoAlertDedupeKey(alert));
  }
}

export interface HodMomoLiveAlertOptions {
  /** The desk replays another moment (Sim off the live edge): seen, never pinged. */
  replaying?: boolean;
}

export function noteHodMomoLiveAlert(
  alert: AlertObject,
  nowMs: number = Date.now(),
  { replaying = false }: HodMomoLiveAlertOptions = {},
): HodMomoPingReason {
  const key = hodMomoAlertDedupeKey(alert);
  if (seenKeys.has(key)) return 'duplicate';
  seenKeys.add(key);
  if (replaying) return 'replaying';
  if (isRunningUpStrategy(alert.strategy_id)) return 'running_up';
  if (!deskSoundAudible('hod')) return 'muted';
  if (lastPingAt > 0 && nowMs - lastPingAt < HOD_MOMO_ALERT_SOUND_COALESCE_MS) {
    return 'coalesced';
  }
  lastPingAt = nowMs;
  playDeskTone('hod', DESK_TONE_HOD);
  return 'pinged';
}

/** Test-only: wipe seen keys, coalesce clock, and re-read the stored pref. */
export function resetHodMomoAlertSoundForTests(): void {
  seenKeys.clear();
  lastPingAt = 0;
  resetDeskTonesForTests();
  resetDeskSoundsForTests();
}
