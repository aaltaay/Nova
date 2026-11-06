/**
 * The one player behind every desk ping, so the sound menu's Play is the sound itself. A tone plays at its sound's
 * volume (deskSounds.ts); each source asks `deskSoundAudible` first. No audio in a window: the alert still shows.
 */
import {
  DESK_TONE_ALARM,
  DESK_TONE_CALL,
  DESK_TONE_HOD,
  DESK_TONE_SETUPS,
  DESK_TONE_TOP_NINE_CHIME,
  DESK_VOICE_SAMPLE,
  type DeskSoundId,
  type DeskTone,
} from './constants';
import { isDeskMuted } from './deskMute';
import { deskSoundGain } from './deskSounds';
import { speakDesk } from './speech';

const PREVIEW_TONES: Partial<Record<DeskSoundId, DeskTone>> = {
  hod: DESK_TONE_HOD,
  setups: DESK_TONE_SETUPS,
  topNine: DESK_TONE_TOP_NINE_CHIME,
  calls: DESK_TONE_CALL,
  alarm: DESK_TONE_ALARM,
};

let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  if (ctx) return ctx;
  try {
    const Ctor = globalThis.AudioContext
      ?? (globalThis as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    ctx = Ctor ? new Ctor() : null;
  } catch {
    ctx = null;
  }
  return ctx;
}

/** A browser holds audio until the page is clicked: a click wakes it. */
export function unlockDeskTones(): void {
  const ac = audio();
  if (ac && ac.state === 'suspended') void ac.resume();
}

export function playDeskTone(id: DeskSoundId, tone: DeskTone): boolean {
  const ac = audio();
  if (!ac) return false;
  try {
    if (ac.state === 'suspended') void ac.resume();
    const peak = deskSoundGain(id, tone.gain);
    let at = ac.currentTime;
    for (const hz of tone.hz) {
      const osc = ac.createOscillator();
      const gain = ac.createGain();
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.frequency.value = hz;
      gain.gain.setValueAtTime(peak, at);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + tone.noteSec);
      osc.start(at);
      osc.stop(at + tone.noteSec + 0.02);
      at += tone.noteSec + tone.gapSec;
    }
    return true;
  } catch {
    return false; // the browser refused to play: the alert still shows
  }
}

/** The menu's Play: the sound at its volume, even with its row off; the header mute still holds. */
export function previewDeskSound(id: DeskSoundId): boolean {
  if (isDeskMuted()) return false;
  if (id === 'voice') return speakDesk(DESK_VOICE_SAMPLE, { evenIfOff: true }) === 'spoken';
  const tone = PREVIEW_TONES[id];
  return tone ? playDeskTone(id, tone) : false;
}

/** Test-only: forget the audio context. */
export function resetDeskTonesForTests(): void {
  ctx = null;
}
