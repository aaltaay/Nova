/**
 * Ahead's per-symbol state (ADR 065): the newest answer the poller read (or why there is none) and whether the Ahead
 * panel is open. One store, so the chart, its heading and the panel read the same answer without asking twice.
 */
import { useSyncExternalStore } from 'react';
import type { AheadAnswer } from './aheadTypes';

export interface AheadHeld {
  answer: AheadAnswer | null;
  /** Words when the last read failed (404 before an API restart, unreachable); null otherwise. */
  problem: string | null;
}

const EMPTY: AheadHeld = { answer: null, problem: null };
const held = new Map<string, AheadHeld>();
const sheets = new Set<string>();
const listeners = new Set<() => void>();

const key = (sym: string) => sym.trim().toUpperCase();

function emit(): void {
  for (const l of listeners) l();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function aheadHeldOf(sym: string): AheadHeld {
  return held.get(key(sym)) ?? EMPTY;
}

export function publishAhead(sym: string, next: AheadHeld): void {
  const k = key(sym);
  const prev = held.get(k) ?? EMPTY;
  if (prev.answer === next.answer && prev.problem === next.problem) return;
  if (next.answer === null && next.problem === null) held.delete(k);
  else held.set(k, next);
  emit();
}

export function clearAhead(sym: string): void {
  publishAhead(sym, EMPTY);
}

export function useAheadHeld(sym: string): AheadHeld {
  return useSyncExternalStore(subscribe, () => aheadHeldOf(sym), () => aheadHeldOf(sym));
}

export function useAheadAnswerOf(sym: string): AheadAnswer | null {
  return useAheadHeld(sym).answer;
}

export function openAheadSheet(sym: string): void {
  if (sheets.has(key(sym))) return;
  sheets.add(key(sym));
  emit();
}

export function closeAheadSheet(sym: string): void {
  if (!sheets.delete(key(sym))) return;
  emit();
}

export function aheadSheetOpen(sym: string): boolean {
  return sheets.has(key(sym));
}

export function useAheadSheetOpen(sym: string): boolean {
  return useSyncExternalStore(subscribe, () => aheadSheetOpen(sym), () => aheadSheetOpen(sym));
}

/** Tests only. */
export function resetAheadStoreForTesting(): void {
  held.clear();
  sheets.clear();
  emit();
}
