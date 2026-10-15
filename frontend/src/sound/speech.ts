/**
 * The desk's voice: the computer's own speech (`speechSynthesis`, an English voice installed on the PC).
 * Nothing is sent anywhere, and the header mute silences it -- mid-word when it is clicked mid-sentence.
 * A window that cannot speak keeps the reason for the mute button's hover (no silent blocker).
 */
import {
  DESK_VOICE_FAILED,
  DESK_VOICE_MAX_QUEUED,
  DESK_VOICE_NO_SPEECH,
  DESK_VOICE_NOT_ALLOWED,
  DESK_VOICE_RATE,
} from './constants';
import { isDeskMuted, subscribeDeskMute } from './deskMute';

export type SpeakResult = 'spoken' | 'muted' | 'unavailable';

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

/** Say `text` unless the desk is muted. Sentences queue; a long queue drops what waits for the newest. */
export function speakDesk(text: string): SpeakResult {
  if (isDeskMuted()) return 'muted';
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

/** Stop speaking now and forget what waits. */
export function hushDesk(): void {
  generation += 1;
  queued = 0;
  synth()?.cancel();
}

subscribeDeskMute((nowMuted) => {
  if (nowMuted) hushDesk();
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
