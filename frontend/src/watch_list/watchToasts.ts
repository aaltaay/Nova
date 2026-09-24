/**
 * Toasts for watched symbols that hit HOD Momo. One toast per symbol: another
 * alert for a symbol already on screen updates that toast (newest alert, one
 * more in the count, its strategy added) and restarts its timer, so a burst of
 * strategies firing together is one toast, not five. Running Up (strategy 12)
 * is its own scanner and never toasts, like the HOD ping.
 */
import { HOD_MOMO_RUNNING_UP_STRATEGY_ID } from '../constants';
import type { AlertObject } from '../hod_momo';
import { WATCH_TOAST_MAX } from './watchListConstants';
import { isWatched } from './watchListStore';

export interface WatchToast {
  symbol: string;
  /** The newest alert for the symbol. */
  alert: AlertObject;
  /** Distinct strategy names, newest first. */
  strategies: readonly string[];
  count: number;
  /** When the newest alert arrived here (ms); the dismiss timer restarts from it. */
  lastAt: number;
}

/** Pure: `toasts` with `alert` folded in, newest toast first, at most `max`. */
export function withWatchAlert(
  toasts: readonly WatchToast[],
  alert: AlertObject,
  nowMs: number,
  max: number = WATCH_TOAST_MAX,
): WatchToast[] {
  const symbol = String(alert.ticker ?? '').trim().toUpperCase();
  if (!symbol) return [...toasts];
  const name = (alert.strategy_name ?? '').trim();
  const prior = toasts.find(t => t.symbol === symbol);
  const strategies = prior
    ? [name, ...prior.strategies.filter(s => s !== name)].filter(Boolean)
    : (name ? [name] : []);
  const next: WatchToast = {
    symbol,
    alert,
    strategies,
    count: (prior?.count ?? 0) + 1,
    lastAt: nowMs,
  };
  return [next, ...toasts.filter(t => t.symbol !== symbol)].slice(0, Math.max(1, max));
}

let toasts: readonly WatchToast[] = [];
const listeners = new Set<() => void>();

function publish(next: readonly WatchToast[]): void {
  toasts = next;
  listeners.forEach(fn => fn());
}

/** A live HOD Momo alert: toast it when its symbol is watched. Returns whether it toasted. */
export function noteWatchedHodAlert(alert: AlertObject, nowMs: number = Date.now()): boolean {
  if (alert.strategy_id === HOD_MOMO_RUNNING_UP_STRATEGY_ID) return false;
  if (!isWatched(String(alert.ticker ?? ''))) return false;
  publish(withWatchAlert(toasts, alert, nowMs));
  return true;
}

export function dismissWatchToast(symbol: string): void {
  const next = toasts.filter(t => t.symbol !== symbol);
  if (next.length !== toasts.length) publish(next);
}

export function getWatchToasts(): readonly WatchToast[] {
  return toasts;
}

export function subscribeWatchToasts(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Test-only. */
export function resetWatchToastsForTests(): void {
  publish([]);
}
