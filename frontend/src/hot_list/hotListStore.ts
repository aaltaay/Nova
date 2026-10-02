/**
 * One poll of today's hot list per window (ADR 044), shared by every part that shows it: the ★ on each
 * Trader tab and the Bots page. It polls only while something is subscribed, and a write answers the
 * new view at once. A failed read keeps the last view and states the error; it never reads as "empty".
 */
import { useSyncExternalStore } from 'react';
import { bringBackYesterday, fetchHotList, patchHotList, starSymbol, unstarSymbol } from './hotListApi';
import { HOT_LIST_POLL_MS } from './constants';
import type { HotListView, HotSide } from './types';

export interface HotListState {
  view: HotListView | null;
  error: string | null;
  busy: boolean;
}

let state: HotListState = { view: null, error: null, busy: false };
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

function set(next: Partial<HotListState>): void {
  state = { ...state, ...next };
  for (const l of listeners) l();
}

async function refresh(): Promise<void> {
  try {
    set({ view: await fetchHotList(), error: null });
  } catch (err) {
    set({ error: err instanceof Error ? err.message : String(err) });
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    void refresh();
    timer = setInterval(() => void refresh(), HOT_LIST_POLL_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

async function write(run: () => Promise<HotListView>): Promise<string | null> {
  set({ busy: true });
  try {
    set({ view: await run(), error: null, busy: false });
    return null;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    set({ busy: false });
    return message;
  }
}

/** Each write answers the backend's refusal in its own words, or null when it took. */
export const hotListActions = {
  star: (symbol: string) => write(() => starSymbol(symbol)),
  unstar: (symbol: string) => write(() => unstarSymbol(symbol)),
  setAuto: (n: number) => write(() => patchHotList({ auto_n: n })),
  setDefault: (buy: HotSide, sell: HotSide) => write(() => patchHotList({ default_buy: buy, default_sell: sell })),
  bringBack: () => write(() => bringBackYesterday()),
  refresh,
};

export function useHotList(): HotListState {
  return useSyncExternalStore(subscribe, () => state, () => state);
}

/** The same state for a reader outside React (the watch list, ADR 044), and its subscription. */
export function getHotListState(): HotListState {
  return state;
}
export const subscribeHotList = subscribe;

/** Whether ``symbol`` is on today's list; null while the list has not been read. */
export function listedOn(view: HotListView | null, symbol: string): boolean | null {
  if (!view) return null;
  const sym = symbol.trim().toUpperCase();
  return view.entries.some(e => e.symbol === sym);
}

export function resetHotListForTests(): void {
  state = { view: null, error: null, busy: false };
  listeners.clear();
  if (timer !== null) clearInterval(timer);
  timer = null;
}
