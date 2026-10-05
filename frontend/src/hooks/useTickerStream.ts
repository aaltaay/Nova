/**
 * The ticker detail stream for React (tickerStore.ts holds it): `useTickerStream` reads all of it and renders
 * on every change; `useTickerSelect` reads one part and renders only when that part changes (#707) -- a
 * Trader panel reads what it shows, so a print renders the panels that show prints and nothing else. The
 * sample desk reads its fixtures and opens nothing.
 */
import { useCallback, useMemo, useRef, useSyncExternalStore } from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { IDLE_TICKER, subscribeTicker, tickerState, type TickerStreamState } from './tickerStore';

export type { TickerStreamState } from './tickerStore';

const noop = () => {};
const keepAll = (s: TickerStreamState) => s;

/** Same keys, each the same value. */
export function shallowEqual<T>(a: T, b: T): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  const ka = Object.keys(a);
  if (ka.length !== Object.keys(b).length) return false;
  return ka.every((k) => Object.is((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]));
}

/**
 * `select` of `symbol`'s stream, rendered again only when `equal` says the selection changed. `select` may be
 * a new function on every render; the selection is kept while it stays equal.
 */
export function useTickerSelect<T>(
  symbol: string | null,
  select: (state: TickerStreamState) => T,
  equal: (a: T, b: T) => boolean = Object.is,
): T {
  const sample = useSampleDataOptional();
  const sampleState = useMemo<TickerStreamState | null>(
    () => (sample && symbol ? { ...IDLE_TICKER, detail: sample.tickerDetail(symbol) } : null),
    [sample, symbol],
  );
  // One line per symbol, whatever case a reader names it in.
  const live = sample || !symbol ? null : symbol.trim().toUpperCase();
  const subscribe = useCallback((onChange: () => void) => (live ? subscribeTicker(live, onChange) : noop), [live]);
  const kept = useRef<{ state: TickerStreamState; select: (s: TickerStreamState) => T; value: T } | null>(null);
  const read = (): T => {
    const state = sampleState ?? tickerState(live);
    const last = kept.current;
    if (last && last.state === state && last.select === select) return last.value;
    const next = select(state);
    const value = last && equal(last.value, next) ? last.value : next;
    kept.current = { state, select, value };
    return value;
  };
  return useSyncExternalStore(subscribe, read, read);
}

/** All of `symbol`'s stream: renders on every message (a print included). */
export function useTickerStream(symbol: string | null): TickerStreamState {
  return useTickerSelect(symbol, keepAll);
}
