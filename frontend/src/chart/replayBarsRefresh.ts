/** ADR 005/012: one replay refresh clock per bar key and one invalidation per seek. */
import { SIM_CHART_REFRESH_MS } from '../sim/simClockEvents';
import { barsStoreKey, invalidateBars } from './barsStore';

const invalidated = new WeakMap<Event, Set<string>>();
const refreshers = new Map<string, { callbacks: Set<() => void>; timer: ReturnType<typeof setInterval> }>();

export function invalidateReplayBars(event: Event | undefined, symbol: string, timeframe: string): void {
  if (event) {
    const key = barsStoreKey(symbol, timeframe);
    let keys = invalidated.get(event);
    if (!keys) { keys = new Set(); invalidated.set(event, keys); }
    if (keys.has(key)) return;
    keys.add(key);
  }
  invalidateBars(symbol, timeframe);
}

/** Synchronous fan-out lets the bar store dedupe chart + VWAP network reads. */
export function subscribeReplayBarsRefresh(symbol: string, timeframe: string, refresh: () => void): () => void {
  const key = barsStoreKey(symbol, timeframe);
  let entry = refreshers.get(key);
  if (!entry) {
    const callbacks = new Set<() => void>();
    entry = { callbacks, timer: setInterval(() => callbacks.forEach(callback => callback()), SIM_CHART_REFRESH_MS) };
    refreshers.set(key, entry);
  }
  entry.callbacks.add(refresh);
  return () => {
    entry.callbacks.delete(refresh);
    if (!entry.callbacks.size) { clearInterval(entry.timer); refreshers.delete(key); }
  };
}
