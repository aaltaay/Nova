/**
 * Rows the operator pinned to the top of a list, for this session only
 * (module state, never persisted -- a pin is a morning gesture, not a
 * preference). One set for every list: a pinned symbol leads wherever it
 * appears.
 */
import { useSyncExternalStore } from 'react';

let pinned: ReadonlySet<string> = new Set<string>();
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

export function getPinnedRows(): ReadonlySet<string> {
  return pinned;
}

export function isRowPinned(symbol: string): boolean {
  return pinned.has(symbol.trim().toUpperCase());
}

export function togglePinnedRow(symbol: string): void {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return;
  const next = new Set(pinned);
  if (next.has(sym)) next.delete(sym);
  else next.add(sym);
  pinned = next;
  emit();
}

export function subscribePinnedRows(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function usePinnedRows(): ReadonlySet<string> {
  return useSyncExternalStore(subscribePinnedRows, getPinnedRows, getPinnedRows);
}

export function usePinnedRow(symbol: string): boolean {
  const set = usePinnedRows();
  return set.has(symbol.trim().toUpperCase());
}

/** Pinned rows first (in their current order), then the rest -- a stable partition. */
export function pinFirst<T extends { symbol: string }>(rows: readonly T[], pins: ReadonlySet<string>): T[] {
  if (pins.size === 0) return [...rows];
  const lead: T[] = [];
  const rest: T[] = [];
  for (const row of rows) {
    (pins.has(row.symbol.toUpperCase()) ? lead : rest).push(row);
  }
  return lead.length === 0 ? [...rows] : [...lead, ...rest];
}

/** Test seam. */
export function _resetPinnedRowsForTests(): void {
  pinned = new Set<string>();
  emit();
}
