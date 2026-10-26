/** One short tick when a stock on the pop-up's screen changes rank. Its own switch (on by default);
 * the header mute (sound/) silences it too. */
import { isDeskMuted } from '../sound';
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';
import { TOP_NINE_SOUND_KEY, TOP_NINE_TICK_GAIN, TOP_NINE_TICK_HZ, TOP_NINE_TICK_SEC } from './topNineConstants';

let ctx: AudioContext | null = null;

export function readTopNineSound(): boolean {
  return readPref(TOP_NINE_SOUND_KEY, true, parseBoolFlag);
}

export function writeTopNineSound(on: boolean): void {
  writePref(TOP_NINE_SOUND_KEY, on);
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

/** Returns what happened, for tests. */
export function tickTopNine(enabled: boolean): 'ticked' | 'muted' | 'silent' {
  if (!enabled || isDeskMuted()) return 'muted';
  const ac = audio();
  if (!ac) return 'silent';
  try {
    if (ac.state === 'suspended') void ac.resume();
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain);
    gain.connect(ac.destination);
    osc.frequency.value = TOP_NINE_TICK_HZ;
    gain.gain.value = TOP_NINE_TICK_GAIN;
    osc.start();
    const end = ac.currentTime + TOP_NINE_TICK_SEC;
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    osc.stop(end + 0.02);
    return 'ticked';
  } catch {
    return 'silent';
  }
}
