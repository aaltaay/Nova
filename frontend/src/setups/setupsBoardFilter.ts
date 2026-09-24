/**
 * Which setup Watchlist › Setups shows (ADR 031), and the "Open board ↗" request a
 * setup card on the Bots page makes. Module state, so the filter survives the tab
 * switching away and back; the open is latched until the Contenders tab consumes
 * it, because that tab mounts after the request (the Bots page is another page).
 * The caller routes the shell to the tab (workspace `requestScannerTab`).
 */
import { useSyncExternalStore } from 'react';

/** Every setup at once. */
export const ALL_SETUPS = 'all';

let filter: string = ALL_SETUPS;
let pendingOpen = false;
const listeners = new Set<() => void>();
const openListeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The board's filter now, outside React. */
export function getSetupsFilter(): string {
  return filter;
}

export function setSetupsFilter(next: string): void {
  if (next === filter) return;
  filter = next;
  listeners.forEach(l => l());
}

/** The board's filter chip: a setup id, or ALL_SETUPS. */
export function useSetupsFilter(): [string, (next: string) => void] {
  return [useSyncExternalStore(subscribe, getSetupsFilter, getSetupsFilter), setSetupsFilter];
}

/** A card's "Open board ↗": filter to `setup` and ask the Contenders tab to show Setups. */
export function requestSetupsBoard(setup: string): void {
  setSetupsFilter(setup);
  pendingOpen = true;
  openListeners.forEach(l => l());
}

/** One-shot: was the Setups board asked for since the last call? */
export function consumeSetupsBoardOpen(): boolean {
  const was = pendingOpen;
  pendingOpen = false;
  return was;
}

export function subscribeSetupsBoardOpen(listener: () => void): () => void {
  openListeners.add(listener);
  return () => {
    openListeners.delete(listener);
  };
}

/** Test helper. */
export function resetSetupsBoardFilterForTests(): void {
  filter = ALL_SETUPS;
  pendingOpen = false;
  listeners.forEach(l => l());
}
