/**
 * The desk's voice: the computer's own speech (`speechSynthesis`, an English voice installed on the PC).
 * Nothing is sent anywhere, and the header mute silences it -- mid-word when it is clicked mid-sentence, as
 * the sound menu's Fill voice switch does. A window that cannot speak keeps the reason for the speaker
 * button's hover (no silent blocker).
 */
import {
  DESK_SOUND_LEVEL_MAX,
  DESK_SOUND_ON_SPOKEN,
  DESK_VOICE_FAILED,
  DESK_VOICE_MAX_QUEUED,
  DESK_VOICE_NO_SPEECH,
  DESK_VOICE_NOT_ALLOWED,
  DESK_VOICE_RATE,
} from './constants';
import { isDeskMuted, setDeskMuted, subscribeDeskMute } from './deskMute';
import { deskSoundAudible, deskSoundLevel, deskSoundOn, subscribeDeskSounds } from './deskSounds';

export type SpeakResult = 'spoken' | 'muted' | 'unavailable';

export interface SpeakOptions {
  /** The sound menu's Play: heard with the Fill voice row off; the header mute still holds. */
  evenIfOff?: boolean;
}

type ProblemListener = (problem: string | null) => void;

const problemListeners = new Set<ProblemListener>();
let problem: string | null = null;
let queued = 0;
/** Bumped by every cancel: a cancelled sentence's late `onerror` / `onend` belongs to an old queue and counts nothing. */
let generation = 0;

function setProblem(next: string | null): void {
  if (next === problem) return;
  problem = next;
  for (const fn of problemListeners) fn(problem);
}

function synth(): SpeechSynthesis | null {
  if (typeof window === 'undefined' || typeof SpeechSynthesisUtterance === 'undefined') return null;
  return window.speechSynthesis ?? null;
}

/** An English voice on this PC, else the default (which may be another language's). */
function englishVoice(s: SpeechSynthesis): SpeechSynthesisVoice | null {
  const voices = s.getVoices();
  return voices.find(v => v.lang === 'en-US' && v.localService)
    ?? voices.find(v => v.lang === 'en-US')
    ?? voices.find(v => v.lang?.toLowerCase().startsWith('en'))
    ?? null;
}

/** Say `text` unless the desk or the voice is muted. Sentences queue; a long queue drops what waits for the newest. */
export function speakDesk(text: string, { evenIfOff = false }: SpeakOptions = {}): SpeakResult {
  if (evenIfOff ? isDeskMuted() : !deskSoundAudible('voice')) return 'muted';
  const s = synth();
  if (!s) {
    setProblem(DESK_VOICE_NO_SPEECH);
    return 'unavailable';
  }
  if (queued >= DESK_VOICE_MAX_QUEUED) hushDesk(); // what waits is older news than this
  const mine = generation;
  const u = new SpeechSynthesisUtterance(text);
  const voice = englishVoice(s);
  if (voice) u.voice = voice;
  u.lang = voice?.lang ?? 'en-US';
  u.rate = DESK_VOICE_RATE;
  u.volume = deskSoundLevel('voice') / DESK_SOUND_LEVEL_MAX;
  u.onend = () => {
    if (mine !== generation) return;
    queued = Math.max(0, queued - 1);
    setProblem(null);
  };
  u.onerror = (ev: SpeechSynthesisErrorEvent) => {
    if (mine !== generation) return;
    queued = Math.max(0, queued - 1);
    // A mute or a full queue cancels on purpose; anything else is a reason the operator did not hear it.
    if (ev.error === 'interrupted' || ev.error === 'canceled') return;
    setProblem(ev.error === 'not-allowed' ? DESK_VOICE_NOT_ALLOWED : `${DESK_VOICE_FAILED} (${ev.error}).`);
    console.warn('[nova] the desk voice could not speak', ev.error, text);
  };
  queued += 1;
  if (s.paused) s.resume(); // Chromium can leave the queue paused after an error
  s.speak(u);
  return 'spoken';
}

/** The speaker's right click and the menu's All sounds. Back on: say so, which proves the speaker works. */
export function flipDeskMute(): void {
  const next = !isDeskMuted();
  setDeskMuted(next);
  if (!next) speakDesk(DESK_SOUND_ON_SPOKEN);
}

/** Stop speaking now and forget what waits. */
export function hushDesk(): void {
  generation += 1;
  queued = 0;
  synth()?.cancel();
}

subscribeDeskMute((nowMuted) => {
  if (nowMuted) hushDesk();
});

let voiceOn = deskSoundOn('voice');
subscribeDeskSounds(() => {
  const next = deskSoundOn('voice');
  if (voiceOn && !next) hushDesk();
  voiceOn = next;
});

export function deskVoiceProblem(): string | null {
  return problem;
}

export function subscribeDeskVoiceProblem(fn: ProblemListener): () => void {
  problemListeners.add(fn);
  return () => {
    problemListeners.delete(fn);
  };
}

/** Test-only. */
export function resetDeskVoiceForTests(): void {
  problem = null;
  queued = 0;
  generation += 1;
}
