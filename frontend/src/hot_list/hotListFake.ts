/**
 * An in-memory hot list for tests (ADR 044): the barrel's shape, with star and unstar answering at once and
 * no backend. A test mocks the barrel with it --
 * `vi.mock('../hot_list', async () => (await import('../hot_list/hotListFake')).hotListFakeModule())` --
 * and drives it through `fakeHotList` (set the list, refuse the next write, reset between tests).
 */
import { useSyncExternalStore } from 'react';
import { HOT_LIST_AUTO_CHOICES } from './constants';
import { normalizeHotList } from './hotListApi';
import type { HotListState } from './hotListStore';
import type { HotHow, HotListView } from './types';

/** A name as a test lists it: a ticker (a ★), or `{symbol, how: 'auto'}` for an auto ☆. */
export type FakeEntry = string | { symbol: string; how: HotHow };

function viewOf(names: readonly FakeEntry[]): HotListView {
  return {
    schema_version: 1, date: '2026-10-01', cap: 20,
    auto: { n: 5, start: '07:00', end: '16:00', rule: null, error: null },
    entries: names.map(n => ({ symbol: typeof n === 'string' ? n : n.symbol, how: typeof n === 'string' ? 'star' : n.how,
      at: 0, board: null, rank: null, change_pct: null, followed: true, why_not_followed: null })),
    yesterday: [], error: null,
  };
}

let state: HotListState = { view: viewOf([]), error: null, busy: false };
let refusal: string | null = null;
const listeners = new Set<() => void>();

function publish(names: readonly FakeEntry[]): void {
  state = { ...state, view: viewOf(names) };
  listeners.forEach(fn => fn());
}

function symbols(): string[] {
  return (state.view?.entries ?? []).map(e => e.symbol);
}

/** Today's names as listed, each with how it came on. */
function names(): FakeEntry[] {
  return (state.view?.entries ?? []).map(e => ({ symbol: e.symbol, how: e.how }));
}

async function write(next: () => FakeEntry[]): Promise<string | null> {
  if (refusal) {
    const said = refusal;
    refusal = null;
    return said;
  }
  publish(next());
  return null;
}

export const fakeHotList = {
  /** Today's list, newest first. */
  set: (list: readonly FakeEntry[]) => publish(list.map(n => (typeof n === 'string' ? n.toUpperCase()
    : { ...n, symbol: n.symbol.toUpperCase() }))),
  /** The next write is refused with these words. */
  refuseNext: (words: string) => { refusal = words; },
  reset: () => { refusal = null; publish([]); },
  symbols,
};

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

export function hotListFakeModule() {
  return {
    getHotListState: () => state,
    subscribeHotList: subscribe,
    useHotList: () => useSyncExternalStore(subscribe, () => state, () => state),
    listedOn: (view: HotListView | null, symbol: string) =>
      (view ? view.entries.some(e => e.symbol === symbol.trim().toUpperCase()) : null),
    howListed: (view: HotListView | null, symbol: string) =>
      (view ? view.entries.find(e => e.symbol === symbol.trim().toUpperCase())?.how ?? null : undefined),
    hotListActions: {
      star: (s: string) => write(() => [s.toUpperCase(), ...names().filter(x => typeof x !== 'string' && x.symbol !== s.toUpperCase())]),
      unstar: (s: string) => write(() => names().filter(x => typeof x !== 'string' && x.symbol !== s.toUpperCase())),
      setAuto: async () => null,
      bringBack: async () => null,
      refresh: async () => {},
    },
    resetHotListForTests: () => fakeHotList.reset(),
    normalizeHotList,
    HOT_LIST_AUTO_CHOICES,
  };
}
