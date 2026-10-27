/**
 * One poll of Claude's seat for the whole window (ADR 068): the pill, its panel, every chart pane's lines and the
 * Level 2 frame read the same status, so the desk asks `/api/agent/trader` once every CLAUDE_SEAT_POLL_MS (slower
 * while the window is hidden), and only while something on screen reads it. The sample desk asks nothing.
 */
import { useSyncExternalStore } from 'react';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { fetchClaudeSeat } from './claudeSeatApi';
import type { ClaudeSeatStatus } from './types';

export const CLAUDE_SEAT_POLL_MS = 1_500;
export const CLAUDE_SEAT_HIDDEN_POLL_MS = 6_000;

export interface ClaudeSeatSnapshot {
  status: ClaudeSeatStatus | null;
  /** Why the last read failed, in words; null while it reads. */
  error: string | null;
}

const EMPTY: ClaudeSeatSnapshot = { status: null, error: null };
let snapshot: ClaudeSeatSnapshot = EMPTY;
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setTimeout> | null = null;
let inFlight: AbortController | null = null;

function publish(next: ClaudeSeatSnapshot): void {
  snapshot = next;
  for (const fn of listeners) fn();
}

function hidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

async function tick(): Promise<void> {
  timer = null;
  if (listeners.size === 0) return;
  inFlight?.abort();
  const ctl = new AbortController();
  inFlight = ctl;
  try {
    const status = await fetchClaudeSeat(ctl.signal);
    if (!ctl.signal.aborted) publish({ status, error: null });
  } catch (err) {
    if (!ctl.signal.aborted) {
      publish({ status: snapshot.status, error: err instanceof Error ? err.message : String(err) });
    }
  } finally {
    if (inFlight === ctl) inFlight = null;
    if (listeners.size > 0 && timer === null) {
      timer = setTimeout(() => { void tick(); }, hidden() ? CLAUDE_SEAT_HIDDEN_POLL_MS : CLAUDE_SEAT_POLL_MS);
    }
  }
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  if (listeners.size === 1 && timer === null && !onSampleDesk()) void tick();
  return () => {
    listeners.delete(fn);
    if (listeners.size === 0) {
      if (timer !== null) clearTimeout(timer);
      timer = null;
      inFlight?.abort();
      inFlight = null;
    }
  };
}

/** Claude's seat as the desk last read it (null: no seat on this backend, or not read yet). */
export function useClaudeSeat(): ClaudeSeatSnapshot {
  return useSyncExternalStore(subscribe, () => snapshot, () => EMPTY);
}

/** A button's answer: show it at once, before the next poll. */
export function applyClaudeSeat(status: ClaudeSeatStatus | null): void {
  if (status) publish({ status, error: null });
}

export function resetClaudeSeatForTests(next: ClaudeSeatSnapshot = EMPTY): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  inFlight?.abort();
  inFlight = null;
  listeners.clear();
  snapshot = next;
}

/** Tests: set what the store holds without a poll. */
export function setClaudeSeatForTests(status: ClaudeSeatStatus | null): void {
  publish({ status, error: null });
}
