/**
 * Live scanner status bridge into GlobalAppBar (one header row).
 * DashboardPage publishes; AppShell's GlobalAppBar subscribes.
 */
import { useSyncExternalStore } from 'react';
import type { GlobalAppBarScanner } from './GlobalAppBar';

let current: GlobalAppBarScanner | null = null;
const listeners = new Set<() => void>();

export function setScannerBarProps(next: GlobalAppBarScanner | null): void {
  current = next;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): GlobalAppBarScanner | null {
  return current;
}

/** GlobalAppBar subscribes here; null while Scanner is not mounted (e.g. Trader). */
export function useScannerBarProps(): GlobalAppBarScanner | null {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
