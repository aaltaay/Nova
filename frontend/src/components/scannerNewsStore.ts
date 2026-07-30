/**
 * Source-tagged news-headline map for HOD Momo News flame join.
 * Dashboard pages publish; HodMomoAlertTable subscribes.
 * Named distinctly from any .tsx -- Windows FS is case-insensitive.
 *
 * Retains the last map across unmount so Trader-view dock keeps flames,
 * but the source tag prevents sample fixtures from leaking into live
 * (leaveSampleView is pushState -- no page reload).
 */
import { useSyncExternalStore } from 'react';

export type ScannerNewsSource = 'live' | 'sample';

type Payload = {
  source: ScannerNewsSource;
  map: Map<string, string>;
};

const EMPTY = new Map<string, string>();

let current: Payload | null = null;
const listeners = new Set<() => void>();

export function setScannerNews(
  source: ScannerNewsSource,
  map: Map<string, string>,
): void {
  current = { source, map };
  listeners.forEach((l) => l());
}

/** Test helper -- clear retained payload. */
export function resetScannerNewsForTests(): void {
  current = null;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): Payload | null {
  return current;
}

/**
 * Returns the map only when the stored source matches `expected`.
 * Mismatch / empty store yields an empty Map (stable empty for memo).
 */
export function useScannerNews(expected: ScannerNewsSource): Map<string, string> {
  const payload = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  if (!payload || payload.source !== expected) return EMPTY;
  return payload.map;
}
