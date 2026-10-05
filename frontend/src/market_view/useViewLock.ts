import { useSyncExternalStore } from 'react';
import { currentViewLock, subscribeViewLocks } from './viewRegistry';

/**
 * Why orders on *symbol* are locked because its market view lags (ADR 045), or null while it is live.
 * Renders only when the lock flips; the registry re-judges every `VIEW_LOCK_TICK_MS` while read.
 */
export function useViewLock(symbol: string | null | undefined): string | null {
  return useSyncExternalStore(
    subscribeViewLocks,
    () => currentViewLock(symbol),
    () => null,
  );
}
