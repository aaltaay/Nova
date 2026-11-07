/**
 * The Level 2 pane's size (operator ask, 2026-11-06: "a right-click on the level 2 ... small, medium, or
 * large"): one choice for every ladder and window, kept between restarts in `nova.level2.size` (a prefStore
 * envelope). Display only -- it scales the pane's type and rows and touches no feed. Another window's change
 * arrives through the `storage` event. Missing, or an unknown value, reads as the default (large, mockup v1 B).
 */
import { useSyncExternalStore } from 'react';
import { L2_SIZES, L2_SIZE_DEFAULT, L2_SIZE_STORAGE_KEY } from '../constants';
import { readPref, writePref } from '../utils/prefStore';

export type Level2Size = (typeof L2_SIZES)[number];

export function parseLevel2Size(raw: unknown): Level2Size | null {
  return typeof raw === 'string' && (L2_SIZES as readonly string[]).includes(raw) ? (raw as Level2Size) : null;
}

function load(): Level2Size {
  if (typeof localStorage === 'undefined') return L2_SIZE_DEFAULT;
  return readPref(L2_SIZE_STORAGE_KEY, L2_SIZE_DEFAULT, parseLevel2Size);
}

let size: Level2Size = load();
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== L2_SIZE_STORAGE_KEY) return;
    size = load();
    emit();
  });
}

export function readLevel2Size(): Level2Size {
  return size;
}

export function setLevel2Size(next: Level2Size): void {
  if (next === size) return;
  size = next;
  // writePref keeps the choice for this session when storage refuses it (the sample desk, a private window).
  if (typeof localStorage !== 'undefined') writePref(L2_SIZE_STORAGE_KEY, size);
  emit();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function useLevel2Size(): Level2Size {
  return useSyncExternalStore(subscribe, readLevel2Size, readLevel2Size);
}

/** Tests only: read storage again as a fresh window would. */
export function reloadLevel2SizeForTesting(): void {
  size = load();
  emit();
}
