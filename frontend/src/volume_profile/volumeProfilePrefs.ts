/**
 * Whether the 5-minute pane shows its profile: one choice for every Trader tab and window, kept across restarts, off
 * until the operator turns it on (ADR 058 decision 2). Another window's change arrives through the `storage` event.
 */
import { useSyncExternalStore } from 'react';
import { VP_PREFS_KEY } from './volumeProfileConstants';

const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return localStorage.getItem(VP_PREFS_KEY) === '1';
  } catch {
    return false;
  }
}

let shown = read();

function emit(): void {
  for (const l of listeners) l();
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== VP_PREFS_KEY) return;
    shown = read();
    emit();
  });
}

export function setProfileShown(next: boolean): void {
  shown = next;
  try {
    localStorage.setItem(VP_PREFS_KEY, next ? '1' : '0');
  } catch {
    /* storage refused (the sample desk): the choice lasts this session */
  }
  emit();
}

export function profileShown(): boolean {
  return shown;
}

export function useProfileShown(): boolean {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => shown,
  );
}
