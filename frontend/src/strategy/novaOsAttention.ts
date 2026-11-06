/**
 * Nova OS attention framework (P3) — muteable toast strip + short Web Audio cues.
 * Kill/risk visuals must remain visible even when muted (sound only is silenced).
 * The cue's switch and volume live in sound/ (the header's sound menu sets them too); the header mute silences it too.
 */
import { NOVA_OS_ATTENTION_COPY } from '../constants';
import { DESK_TONE_ALARM, deskSoundAudible, deskSoundOn, playDeskTone, setDeskSoundOn } from '../sound';

/** The verdict, staged-ticket, fill and mode-reset kinds went with the Nova OS
 * verdict and the executor (ADR 025); these three still come from the event log. */
export type NovaOsAttentionKind = 'risk_halt' | 'kill' | 'archive_fail';

export interface NovaOsAttentionEvent {
  id: string;
  kind: NovaOsAttentionKind;
  message: string;
  symbol?: string;
  ts: number;
}

type Listener = (events: NovaOsAttentionEvent[]) => void;

const MAX_EVENTS = 8;
let events: NovaOsAttentionEvent[] = [];
const listeners = new Set<Listener>();

function emit() {
  const snapshot = [...events];
  for (const listener of listeners) listener(snapshot);
}

/** One low alarm tone: every remaining kind (kill, risk halt, archive failure) is a warning. Web Audio unavailable: the strip still works. */
function playCue() {
  if (deskSoundAudible('alarm')) playDeskTone('alarm', DESK_TONE_ALARM);
}

export function isNovaOsAttentionMuted(): boolean {
  return !deskSoundOn('alarm');
}

export function setNovaOsAttentionMuted(next: boolean): void {
  setDeskSoundOn('alarm', !next);
  emit();
}

export function subscribeNovaOsAttention(listener: Listener): () => void {
  listeners.add(listener);
  listener([...events]);
  return () => {
    listeners.delete(listener);
  };
}

export function pushNovaOsAttention(
  kind: NovaOsAttentionKind,
  opts?: { symbol?: string; message?: string },
): void {
  const event: NovaOsAttentionEvent = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    kind,
    message: opts?.message ?? NOVA_OS_ATTENTION_COPY[kind] ?? kind,
    symbol: opts?.symbol,
    ts: Date.now(),
  };
  events = [event, ...events].slice(0, MAX_EVENTS);
  playCue();
  emit();
}

export function dismissNovaOsAttention(id: string): void {
  events = events.filter((e) => e.id !== id);
  emit();
}

export function clearNovaOsAttention(): void {
  events = [];
  emit();
}
