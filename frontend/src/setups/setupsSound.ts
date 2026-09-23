/** One short ping when the bot raises a proposal (a setup near its trigger with
 * the tape saying go). Its own mute switch, separate from HOD Momo's. */
import {
  SETUPS_PING_GAIN,
  SETUPS_PING_HZ,
  SETUPS_PING_SEC,
  SETUPS_SOUND_STORAGE_KEY,
} from '../constants';

type Listener = (enabled: boolean) => void;

const heard = new Set<string>();
const listeners = new Set<Listener>();
let enabled = readEnabled();
let ctx: AudioContext | null = null;

function readEnabled(): boolean {
  try {
    return window.localStorage.getItem(SETUPS_SOUND_STORAGE_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function isSetupsSoundEnabled(): boolean {
  return enabled;
}

export function setSetupsSoundEnabled(next: boolean): void {
  enabled = next;
  try {
    window.localStorage.setItem(SETUPS_SOUND_STORAGE_KEY, next ? 'on' : 'off');
  } catch {
    // storage blocked: the switch still works for this page
  }
  for (const fn of listeners) fn(enabled);
}

export function subscribeSetupsSound(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function audio(): AudioContext | null {
  if (ctx) return ctx;
  try {
    const Ctor = window.AudioContext
      ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    ctx = Ctor ? new Ctor() : null;
  } catch {
    ctx = null;
  }
  return ctx;
}

function ping(): boolean {
  const ac = audio();
  if (!ac) return false;
  try {
    if (ac.state === 'suspended') void ac.resume();
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain);
    gain.connect(ac.destination);
    osc.frequency.value = SETUPS_PING_HZ;
    gain.gain.value = SETUPS_PING_GAIN;
    osc.start();
    const end = ac.currentTime + SETUPS_PING_SEC;
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    osc.stop(end + 0.02);
    return true;
  } catch {
    return false;
  }
}

/** Ping once per proposal id. Returns what happened, for tests. */
export function noteSetupProposal(id: string): 'pinged' | 'duplicate' | 'muted' | 'silent' {
  if (heard.has(id)) return 'duplicate';
  heard.add(id);
  if (!enabled) return 'muted';
  return ping() ? 'pinged' : 'silent';
}

export function resetSetupsSoundForTests(): void {
  heard.clear();
  ctx = null;
  enabled = readEnabled();
}
