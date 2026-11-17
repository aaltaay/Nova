/**
 * One poll of the traders view for the whole window (ADR 072): the brain's pill, its panel and the Level 2 frame
 * read the same status, so the desk asks `/api/traders` once every BRAIN_SEAT_POLL_MS (slower while the window is
 * hidden), and only while something on screen reads it. A read that fails keeps the last status and says why. The
 * sample desk asks nothing.
 */
import { useSyncExternalStore } from 'react';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { fetchBrainSeat } from './brainSeatApi';
import type { BrainSeatStatus } from './types';

export const BRAIN_SEAT_POLL_MS = 1_500;
export const BRAIN_SEAT_HIDDEN_POLL_MS = 6_000;

export interface BrainSeatSnapshot {
  status: BrainSeatStatus | null;
  /** Why the last read failed, in words; null while it reads. */
  error: string | null;
}

const EMPTY: BrainSeatSnapshot = { status: null, error: null };
let snapshot: BrainSeatSnapshot = EMPTY;
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setTimeout> | null = null;
let inFlight: AbortController | null = null;

function publish(next: BrainSeatSnapshot): void {
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
    const status = await fetchBrainSeat(ctl.signal);
    if (!ctl.signal.aborted) publish({ status, error: null });
  } catch (err) {
    if (!ctl.signal.aborted) {
      publish({ status: snapshot.status, error: err instanceof Error ? err.message : String(err) });
    }
  } finally {
    if (inFlight === ctl) inFlight = null;
    if (listeners.size > 0 && timer === null) {
      timer = setTimeout(() => { void tick(); }, hidden() ? BRAIN_SEAT_HIDDEN_POLL_MS : BRAIN_SEAT_POLL_MS);
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

/** The brain as the desk last read it (null: no traders view on this backend, or not read yet). */
export function useBrainSeat(): BrainSeatSnapshot {
  return useSyncExternalStore(subscribe, () => snapshot, () => EMPTY);
}

/** The switch's answer: show it at once, before the next poll. */
export function applyBrainSeat(status: BrainSeatStatus | null): void {
  if (status) publish({ status, error: null });
}

export function resetBrainSeatForTests(next: BrainSeatSnapshot = EMPTY): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  inFlight?.abort();
  inFlight = null;
  listeners.clear();
  snapshot = next;
}

/** Tests: set what the store holds without a poll. */
export function setBrainSeatForTests(status: BrainSeatStatus | null, error: string | null = null): void {
  publish({ status, error });
}
