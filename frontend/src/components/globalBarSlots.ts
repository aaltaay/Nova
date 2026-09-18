/**
 * Portal target for the Trader tab strip inside GlobalAppBar's middle column.
 * StockViewTabs owns the tabs (state + handlers); the header only offers the
 * slot element. When no slot is mounted (Trader hidden, tests), the strip
 * renders inline so nothing depends on the header being present.
 */
import { useSyncExternalStore } from 'react';

let slot: HTMLElement | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

/** GlobalAppBar callback ref -- null on unmount.
 * Emit after this commit so StockViewTabs is not updated while GlobalAppBar
 * is still committing (React 19 + StrictMode). */
export function setGlobalBarTraderSlot(el: HTMLElement | null): void {
  if (slot === el) return;
  slot = el;
  queueMicrotask(() => {
    if (slot === el) emit();
  });
}

export function getGlobalBarTraderSlot(): HTMLElement | null {
  return slot;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useGlobalBarTraderSlot(): HTMLElement | null {
  return useSyncExternalStore(subscribe, getGlobalBarTraderSlot, () => null);
}

/** Test helper. */
export function resetGlobalBarSlotsForTests(): void {
  slot = null;
  emit();
}
