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
 * Sim off the live edge (#486): the strip shows another moment, so a live
 * alert that arrives then is marked seen without a ping -- and, being seen,
 * never pings late once the desk is back at the live edge.
 */
import {
  HOD_MOMO_ALERT_PING_GAIN,
  HOD_MOMO_ALERT_PING_HZ,
  HOD_MOMO_ALERT_PING_SEC,
  HOD_MOMO_ALERT_SOUND_COALESCE_MS,
  HOD_MOMO_ALERT_SOUND_DEFAULT,
  HOD_MOMO_ALERT_SOUND_KEY,
} from './hodMomoAlertSoundConstants';
import { isRunningUpStrategy } from './scannerPartition';
import type { AlertObject } from './types';
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';

export type HodMomoPingReason =
  | 'pinged'
  | 'coalesced'
  | 'muted'
  | 'duplicate'
  | 'running_up'
  | 'replaying';

type Listener = (enabled: boolean) => void;

const listeners = new Set<Listener>();
const seenKeys = new Set<string>();
let enabled = HOD_MOMO_ALERT_SOUND_DEFAULT;
let lastPingAt = 0;
let audioCtx: AudioContext | null = null;

function readEnabled(): boolean {
  return readPref(HOD_MOMO_ALERT_SOUND_KEY, HOD_MOMO_ALERT_SOUND_DEFAULT, parseBoolFlag);
}

enabled = readEnabled();

function emit(): void {
  const snapshot = enabled;
  for (const listener of listeners) listener(snapshot);
}

export function hodMomoAlertDedupeKey(
  alert: Pick<AlertObject, 'id' | 'ticker' | 'timestamp'>,
): string {
  const id = typeof alert.id === 'string' ? alert.id.trim() : '';
  if (id) return `id:${id}`;
  const ticker = String(alert.ticker ?? '').trim().toUpperCase();
  return `sym:${ticker}|${alert.timestamp ?? ''}`;
}

export function isHodMomoAlertSoundEnabled(): boolean {
  return enabled;
}

export function setHodMomoAlertSoundEnabled(next: boolean): void {
  enabled = next;
  writePref(HOD_MOMO_ALERT_SOUND_KEY, next);
  if (next) unlockHodMomoAlertAudio();
  emit();
}

export function subscribeHodMomoAlertSound(listener: Listener): () => void {
  listeners.add(listener);
  listener(enabled);
  return () => {
    listeners.delete(listener);
  };
}

export function rememberHodMomoAlertSnapshot(alerts: readonly AlertObject[]): void {
  seenKeys.clear();
  for (const alert of alerts) {
    seenKeys.add(hodMomoAlertDedupeKey(alert));
  }
}

function ensureAudioCtx(): AudioContext | null {
  if (audioCtx) return audioCtx;
  try {
    const Ctor =
      typeof AudioContext !== 'undefined'
        ? AudioContext
        : (globalThis as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    audioCtx = new Ctor();
    return audioCtx;
  } catch {
    return null;
  }
}

export function unlockHodMomoAlertAudio(): void {
  const ctx = ensureAudioCtx();
  if (ctx && ctx.state === 'suspended') {
    void ctx.resume();
  }
}

function playPing(): boolean {
  if (!enabled) return false;
  try {
    const ctx = ensureAudioCtx();
    if (!ctx) return false;
    if (ctx.state === 'suspended') void ctx.resume();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = HOD_MOMO_ALERT_PING_HZ;
    gain.gain.value = HOD_MOMO_ALERT_PING_GAIN;
    osc.start();
    const end = ctx.currentTime + HOD_MOMO_ALERT_PING_SEC;
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    osc.stop(end + 0.02);
    return true;
  } catch {
    return false;
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
  if (!enabled) return 'muted';
  if (lastPingAt > 0 && nowMs - lastPingAt < HOD_MOMO_ALERT_SOUND_COALESCE_MS) {
    return 'coalesced';
  }
  lastPingAt = nowMs;
  playPing();
  return 'pinged';
}

/** Test-only: wipe seen keys, coalesce clock, and re-read the stored pref. */
export function resetHodMomoAlertSoundForTests(): void {
  seenKeys.clear();
  lastPingAt = 0;
  audioCtx = null;
  enabled = readEnabled();
}
