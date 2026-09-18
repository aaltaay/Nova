/**
 * Desk-level HOD Momo new-row ping (localStorage mute + short Web Audio cue).
 *
 * Same oscillator pattern as `strategy/novaOsAttention.ts` (quiet sine, ~160ms).
 * Not StrategyConfig.audio -- that is a per-strategy backend checkbox with no
 * playback consumer. Running Up does not use this cue.
 */
export const HOD_MOMO_ALERT_SOUND_KEY = 'nova.hodMomo.alertSound.on';
export const HOD_MOMO_ALERT_SOUND_DEFAULT = true;
/** One ping if several new HOD rows land in one flush or within this window. */
export const HOD_MOMO_ALERT_SOUND_COALESCE_MS = 400;
const PING_FREQ_HZ = 880;
const PING_GAIN = 0.03;
const PING_SEC = 0.16;

type SoundListener = (on: boolean) => void;

let soundOn = HOD_MOMO_ALERT_SOUND_DEFAULT;
let lastPingAt = 0;
let audioCtx: AudioContext | null = null;
const listeners = new Set<SoundListener>();

function readSoundOn(): boolean {
  try {
    const raw = localStorage.getItem(HOD_MOMO_ALERT_SOUND_KEY);
    if (raw == null) return HOD_MOMO_ALERT_SOUND_DEFAULT;
    return raw !== '0' && raw !== 'false';
  } catch {
    return HOD_MOMO_ALERT_SOUND_DEFAULT;
  }
}

soundOn = readSoundOn();

function emit() {
  for (const listener of listeners) listener(soundOn);
}

export function isHodMomoAlertSoundOn(): boolean {
  return soundOn;
}

export function setHodMomoAlertSoundOn(next: boolean): void {
  soundOn = next;
  try {
    localStorage.setItem(HOD_MOMO_ALERT_SOUND_KEY, next ? '1' : '0');
  } catch {
    /* private mode / quota */
  }
  emit();
}

export function subscribeHodMomoAlertSound(listener: SoundListener): () => void {
  listeners.add(listener);
  listener(soundOn);
  return () => {
    listeners.delete(listener);
  };
}

export function unlockHodMomoAlertAudio(): void {
  try {
    const ctx = ensureAudioCtx();
    if (ctx && ctx.state === 'suspended') void ctx.resume();
  } catch {
    /* Web Audio unavailable */
  }
}

function ensureAudioCtx(): AudioContext | null {
  if (audioCtx) return audioCtx;
  const AC =
    typeof AudioContext !== 'undefined'
      ? AudioContext
      : (globalThis as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AC) return null;
  audioCtx = new AC();
  return audioCtx;
}

function playCue(): void {
  try {
    const ctx = ensureAudioCtx();
    if (!ctx) return;
    if (ctx.state === 'suspended') void ctx.resume();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = PING_FREQ_HZ;
    gain.gain.value = PING_GAIN;
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + PING_SEC);
    osc.stop(ctx.currentTime + PING_SEC + 0.02);
  } catch {
    /* visual list still works */
  }
}

/** @returns true when a cue was started (on, not coalesced). */
export function playHodMomoAlertPing(now = Date.now()): boolean {
  if (!soundOn) return false;
  if (now - lastPingAt < HOD_MOMO_ALERT_SOUND_COALESCE_MS) return false;
  lastPingAt = now;
  playCue();
  return true;
}

export function resetHodMomoAlertSoundForTests(): void {
  soundOn = HOD_MOMO_ALERT_SOUND_DEFAULT;
  lastPingAt = 0;
  audioCtx = null;
  try {
    localStorage.removeItem(HOD_MOMO_ALERT_SOUND_KEY);
  } catch {
    /* ignore */
  }
}
