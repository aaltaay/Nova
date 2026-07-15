/**
 * Nova OS attention framework (P3) — muteable toast strip + short Web Audio cues.
 * Kill/risk visuals must remain visible even when muted (sound only is silenced).
 */
import {
  NOVA_OS_ATTENTION_COPY,
  NOVA_OS_ATTENTION_MUTE_STORAGE_KEY,
  NOVA_OS_ATTENTION_MUTED_DEFAULT,
} from '../constants';

export type NovaOsAttentionKind =
  | 'decision_buy'
  | 'decision_wait'
  | 'decision_no_buy'
  | 'mode_reset'
  | 'risk_halt'
  | 'staged'
  | 'expired'
  | 'fill'
  | 'stop'
  | 'kill'
  | 'archive_fail';

export interface NovaOsAttentionEvent {
  id: string;
  kind: NovaOsAttentionKind;
  message: string;
  symbol?: string;
  ts: number;
}

type Listener = (events: NovaOsAttentionEvent[]) => void;

const MAX_EVENTS = 8;
let muted = NOVA_OS_ATTENTION_MUTED_DEFAULT;
let events: NovaOsAttentionEvent[] = [];
const listeners = new Set<Listener>();
let audioCtx: AudioContext | null = null;

function readMute(): boolean {
  try {
    const raw = localStorage.getItem(NOVA_OS_ATTENTION_MUTE_STORAGE_KEY);
    if (raw == null) return NOVA_OS_ATTENTION_MUTED_DEFAULT;
    return raw === '1' || raw === 'true';
  } catch {
    return NOVA_OS_ATTENTION_MUTED_DEFAULT;
  }
}

muted = readMute();

function emit() {
  const snapshot = [...events];
  for (const listener of listeners) listener(snapshot);
}

function playCue(kind: NovaOsAttentionKind) {
  if (muted) return;
  try {
    if (!audioCtx) audioCtx = new AudioContext();
    const ctx = audioCtx;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    const freq =
      kind === 'decision_buy' || kind === 'fill'
        ? 880
        : kind === 'risk_halt' || kind === 'kill' || kind === 'archive_fail'
          ? 220
          : kind === 'decision_wait' || kind === 'expired'
            ? 520
            : 440;
    osc.frequency.value = freq;
    gain.gain.value = 0.04;
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);
    osc.stop(ctx.currentTime + 0.2);
  } catch {
    // Web Audio unavailable — visual strip still works.
  }
}

export function isNovaOsAttentionMuted(): boolean {
  return muted;
}

export function setNovaOsAttentionMuted(next: boolean): void {
  muted = next;
  try {
    localStorage.setItem(NOVA_OS_ATTENTION_MUTE_STORAGE_KEY, next ? '1' : '0');
  } catch {
    // ignore quota / private mode
  }
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
  playCue(kind);
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

/** Map a decide() verdict to an attention kind (signal-mode receipts). */
export function attentionKindForDecision(decision: string): NovaOsAttentionKind {
  if (decision === 'BUY') return 'decision_buy';
  if (decision === 'WAIT') return 'decision_wait';
  return 'decision_no_buy';
}
