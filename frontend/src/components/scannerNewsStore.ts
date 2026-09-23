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
import type { CatalystVerdict } from '../types/catalystVerdict';

export type ScannerNewsSource = 'live' | 'sample';

/** Symbol -> the row's catalyst verdict (ADR 024); only symbols whose row carries the field. */
export type CatalystBySymbol = Map<string, CatalystVerdict | null>;

type Payload = {
  source: ScannerNewsSource;
  map: Map<string, string>;
  catalysts: CatalystBySymbol;
};

const EMPTY = new Map<string, string>();
const EMPTY_CATALYSTS: CatalystBySymbol = new Map();

let current: Payload | null = null;
const listeners = new Set<() => void>();

export function setScannerNews(
  source: ScannerNewsSource,
  map: Map<string, string>,
  catalysts: CatalystBySymbol = EMPTY_CATALYSTS,
): void {
  current = { source, map, catalysts };
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

/** The rows' catalyst verdicts, on the same source rule as `useScannerNews`. */
export function useScannerCatalysts(expected: ScannerNewsSource): CatalystBySymbol {
  const payload = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  if (!payload || payload.source !== expected) return EMPTY_CATALYSTS;
  return payload.catalysts;
}
