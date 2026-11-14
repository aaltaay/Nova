/**
 * The phone's Level 2 marks switch (ADR 070 amendment 2026-11-13): the desk's marks on the phone's book and the
 * depth chart under it. On until the operator turns it off in Settings (the operator picked the look with them);
 * kept on the phone in `nova.phone.level2.marks`, a prefStore envelope. Off, the book is the plain one it was.
 */
import { useSyncExternalStore } from 'react';
import { parseBoolFlag, readPref, writePref } from '../../utils/prefStore';

export const LEVEL2_MARKS_KEY = 'nova.phone.level2.marks';

function load(): boolean {
  if (typeof localStorage === 'undefined') return true;
  return readPref(LEVEL2_MARKS_KEY, true, parseBoolFlag);
}

let on = load();
const listeners = new Set<() => void>();

export function readLevel2Marks(): boolean {
  return on;
}

export function setLevel2Marks(next: boolean): void {
  if (next === on) return;
  on = next;
  if (typeof localStorage !== 'undefined') writePref(LEVEL2_MARKS_KEY, on);
  for (const l of listeners) l();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function useLevel2Marks(): boolean {
  return useSyncExternalStore(subscribe, readLevel2Marks, readLevel2Marks);
}

/** Tests only: read storage again as a fresh page would. */
export function reloadLevel2MarksForTesting(): void {
  on = load();
  for (const l of listeners) l();
}
