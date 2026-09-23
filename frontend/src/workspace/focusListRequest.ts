/**
 * The scanner list a symbol was just picked from, for the Trader's Focus rail
 * to follow (operator ask 2026-09-23: open a ticker from Gainers and Focus
 * shows Gainers). Latched until the rail consumes it -- the rail may mount
 * after the open -- and announced to a rail already mounted. The rail decides
 * whether it can mirror the list; an open with no list leaves Focus as it was.
 */
import { isTabModuleId } from './registry';

let pending: string | null = null;
const listeners = new Set<() => void>();

export function requestFocusList(list: string | null | undefined): void {
  if (!list || !isTabModuleId(list)) return;
  pending = list;
  for (const listener of listeners) listener();
}

/** One-shot: the pending list, or null. The rail calls this on mount and on each request. */
export function consumeFocusListRequest(): string | null {
  const list = pending;
  pending = null;
  return list;
}

export function subscribeFocusListRequest(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
