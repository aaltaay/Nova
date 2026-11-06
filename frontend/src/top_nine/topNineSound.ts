/** The pop-up's sounds (operator ask, 2026-10-27: "When the menu switches ... I need to hear the sound"):
 * a two-note chime when a stock on screen moves up or comes in, at most once per TOP_NINE_CHIME_COOLDOWN_MS --
 * a switch inside that window stays quiet, it is not queued -- and three short beeps when one halts, which no
 * cooldown holds back. Its own switch (on by default); the header mute (sound/) silences both. */
import { isDeskMuted } from '../sound';
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';
import {
  TOP_NINE_CHIME_COOLDOWN_MS,
  TOP_NINE_CHIME_GAIN,
  TOP_NINE_CHIME_NOTE_SEC,
  TOP_NINE_CHIME_NOTES_HZ,
  TOP_NINE_HALT_GAIN,
  TOP_NINE_HALT_GAP_SEC,
  TOP_NINE_HALT_NOTE_SEC,
  TOP_NINE_HALT_NOTES_HZ,
  TOP_NINE_SOUND_KEY,
} from './topNineConstants';

export type TopNineSoundResult = 'played' | 'cooldown' | 'muted' | 'silent';

let ctx: AudioContext | null = null;
let lastChimeAt: number | null = null;

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

/** A browser holds audio until the page is clicked: the pop-up's first click wakes it. */
export function unlockTopNineAudio(): void {
  const ac = audio();
  if (ac && ac.state === 'suspended') void ac.resume();
}

function playNotes(notes: readonly number[], noteSec: number, gapSec: number, peak: number): boolean {
  const ac = audio();
  if (!ac) return false;
  try {
    if (ac.state === 'suspended') void ac.resume();
    let at = ac.currentTime;
    for (const hz of notes) {
      const osc = ac.createOscillator();
      const gain = ac.createGain();
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.frequency.value = hz;
      gain.gain.setValueAtTime(peak, at);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + noteSec);
      osc.start(at);
      osc.stop(at + noteSec + 0.02);
      at += noteSec + gapSec;
    }
    return true;
  } catch {
    return false;
  }
}

/** A switch worth hearing. Returns what happened, for tests; only a played chime starts the cooldown. */
export function chimeTopNine(enabled: boolean, now: number = Date.now()): TopNineSoundResult {
  if (!enabled || isDeskMuted()) return 'muted';
  if (lastChimeAt != null && now - lastChimeAt < TOP_NINE_CHIME_COOLDOWN_MS) return 'cooldown';
  if (!playNotes(TOP_NINE_CHIME_NOTES_HZ, TOP_NINE_CHIME_NOTE_SEC, 0, TOP_NINE_CHIME_GAIN)) return 'silent';
  lastChimeAt = now;
  return 'played';
}

/** A stock on screen halted. */
export function beepTopNineHalt(enabled: boolean): TopNineSoundResult {
  if (!enabled || isDeskMuted()) return 'muted';
  return playNotes(TOP_NINE_HALT_NOTES_HZ, TOP_NINE_HALT_NOTE_SEC, TOP_NINE_HALT_GAP_SEC, TOP_NINE_HALT_GAIN)
    ? 'played'
    : 'silent';
}

/** Test-only: forget the audio context and the last chime. */
export function resetTopNineSoundForTests(): void {
  ctx = null;
  lastChimeAt = null;
}
