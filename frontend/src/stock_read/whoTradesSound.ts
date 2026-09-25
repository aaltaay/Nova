/**
 * The chart's ping (ADR 037): one short sound per call -- ENTER NOW, SELL NOW, what Nova just did --
 * keyed on the call's id, so a call that stays on screen pings once per page. Its own mute,
 * `nova.stockRead.sound` = `{schema_version: 1, value: boolean}`, shared by every Trader tab.
 */
import { readPref, writePref } from '../utils/prefStore';
import { STOCK_MODE_SOUND_KEY } from './constants';
import type { CallTone } from './momentModel';

type Listener = (enabled: boolean) => void;

/** Two notes for a call to act (enter, sell), one for Nova's news. */
const NOTES: Partial<Record<CallTone, number[]>> = {
  go: [880, 1175],
  target: [988, 740],
  stop: [659, 440],
  nova: [784],
  done: [1047],
};
const NOTE_SEC = 0.11;
const GAIN = 0.06;

const heard = new Set<string>();
const listeners = new Set<Listener>();
let enabled = readEnabled();
let ctx: AudioContext | null = null;

function readEnabled(): boolean {
  if (typeof localStorage === 'undefined') return true; // no storage (a worker, a test): the ping is on
  return readPref(STOCK_MODE_SOUND_KEY, true, raw => (typeof raw === 'boolean' ? raw : null));
}

export function isStockReadSoundOn(): boolean {
  return enabled;
}

export function setStockReadSound(next: boolean): void {
  enabled = next;
  writePref(STOCK_MODE_SOUND_KEY, next);
  for (const fn of listeners) fn(enabled);
}

export function subscribeStockReadSound(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function audio(): AudioContext | null {
  if (ctx) return ctx;
  try {
    const Ctor = window.AudioContext
      ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    ctx = Ctor ? new Ctor() : null;
  } catch {
    ctx = null; // no audio in this window: the call still shows
  }
  return ctx;
}

function play(notes: number[]): boolean {
  const ac = audio();
  if (!ac) return false;
  try {
    if (ac.state === 'suspended') void ac.resume();
    notes.forEach((hz, n) => {
      const osc = ac.createOscillator();
      const gain = ac.createGain();
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.frequency.value = hz;
      const start = ac.currentTime + n * (NOTE_SEC + 0.03);
      gain.gain.setValueAtTime(GAIN, start);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + NOTE_SEC);
      osc.start(start);
      osc.stop(start + NOTE_SEC + 0.02);
    });
    return true;
  } catch {
    return false; // the browser refused to play: the call still shows
  }
}

/** Ping once per call id. Returns what happened, for tests. */
export function pingCall(id: string, tone: CallTone): 'pinged' | 'duplicate' | 'muted' | 'silent' {
  if (heard.has(id)) return 'duplicate';
  heard.add(id);
  if (!enabled) return 'muted';
  const notes = NOTES[tone];
  return notes && play(notes) ? 'pinged' : 'silent';
}

export function resetStockReadSoundForTests(): void {
  heard.clear();
  ctx = null;
  enabled = readEnabled();
}
