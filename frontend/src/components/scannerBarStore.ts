/**
 * Shared GlobalAppBar status strip store (Scanner + Trader).
 * AppShell's GlobalBarStatusBridge publishes the always-on chrome.
 * Dashboard may patch price-freshness only -- never clears the whole bar.
 */
import { useSyncExternalStore } from 'react';
import type { GlobalAppBarScanner } from './globalAppBarScanner';

let current: GlobalAppBarScanner | null = null;
let historyDate: string | null = null;
let historyDates: string[] = [];
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

export function getScannerBarSnapshot(): GlobalAppBarScanner | null {
  return current;
}

export function setGlobalBarHistoryDate(date: string | null): void {
  historyDate = date;
  if (current) {
    current = { ...current, historyDate };
    emit();
  }
}

export function setGlobalBarHistoryDates(dates: string[]): void {
  historyDates = dates;
  if (current) {
    current = { ...current, historyDates };
    emit();
  }
}

/**
 * Publish bridge-owned fields while preserving Dashboard freshness patches
 * and shared history selection.
 */
export function publishGlobalBarCore(
  core:     Omit<
    GlobalAppBarScanner,
    | 'secondsAgo'
    | 'pricesStale'
    | 'lastPriceTs'
    | 'honestyText'
    | 'historyDate'
    | 'historyDates'
  >,
): void {
  current = {
    ...core,
    historyDate,
    historyDates,
    secondsAgo: current?.secondsAgo ?? null,
    pricesStale: current?.pricesStale ?? false,
    lastPriceTs: current?.lastPriceTs ?? null,
    honestyText: current?.honestyText ?? null,
    onBackendStarted: current?.onBackendStarted ?? core.onBackendStarted,
  };
  emit();
}

/** Merge fields without wiping the strip (Dashboard freshness). */
export function patchScannerBarProps(partial: Partial<GlobalAppBarScanner>): void {
  if (!current) return;
  if ('historyDate' in partial && partial.historyDate !== undefined) {
    historyDate = partial.historyDate;
  }
  if ('historyDates' in partial && partial.historyDates !== undefined) {
    historyDates = partial.historyDates;
  }
  current = { ...current, ...partial };
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** GlobalAppBar subscribes here -- non-null once AppShell bridge has published. */
export function useScannerBarProps(): GlobalAppBarScanner | null {
  return useSyncExternalStore(subscribe, getScannerBarSnapshot, getScannerBarSnapshot);
}

/** Test helper. */
export function resetScannerBarStoreForTests(): void {
  current = null;
  historyDate = null;
  historyDates = [];
  emit();
}
