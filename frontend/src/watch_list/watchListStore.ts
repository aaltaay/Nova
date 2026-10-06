/**
 * The watch list is today's hot list (ADR 044: "the watch list folds into the ★"). Every Watch action on
 * the desk -- a scanner row, the chart menu, the Desk board, the Hot list tab -- stars or unstars the
 * stock on the hot list (`hot_list`), and the watch toasts follow the listed names. The list is the
 * backend's: one for every window, fresh at 04:00 ET, up to its cap. A write shows at once and is undone
 * when the backend refuses it, which is said in the backend's own words, never silent.
 *
 * The list this desk kept before the fold (`nova.watch.list`, `{schema_version: 1, symbols}`; an unknown
 * version is ignored, never guessed) is only read now: the Hot list tab offers to star it, then it is
 * forgotten. The sample desk (#449) keeps a list of its own, in memory, starting empty, and sends nothing.
 */
import { useSyncExternalStore } from 'react';
import { getHotListState, hotListActions, resetHotListForTests, subscribeHotList } from '../hot_list';
import { isSampleView } from '../sample_data/sampleNav';
import { alertApp } from '../ux/appDialogApi';
import {
  WATCH_LIST_MAX,
  WATCH_LIST_SCHEMA_VERSION,
  WATCH_LIST_STORAGE_KEY,
  WATCH_LIST_SYMBOL_RE,
} from './watchListConstants';

const EMPTY: readonly string[] = [];

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** Upper-cased ticker, or null when the text cannot be one. */
export function normalizeWatchSymbol(raw: string): string | null {
  const symbol = raw.trim().toUpperCase();
  return WATCH_LIST_SYMBOL_RE.test(symbol) ? symbol : null;
}

/** The list this desk saved before the hot list, newest first (read only; empty when none). */
export function readSavedWatchList(): readonly string[] {
  const store = storage();
  if (!store) return EMPTY;
  try {
    const raw = store.getItem(WATCH_LIST_STORAGE_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as { schema_version?: unknown; symbols?: unknown };
    if (parsed.schema_version !== WATCH_LIST_SCHEMA_VERSION) {
      console.warn('[nova] ignoring a saved watch list with unknown schema_version', parsed.schema_version);
      return EMPTY;
    }
    if (!Array.isArray(parsed.symbols)) return EMPTY;
    const symbols = parsed.symbols
      .map(s => (typeof s === 'string' ? normalizeWatchSymbol(s) : null))
      .filter((s): s is string => s !== null);
    return [...new Set(symbols)].slice(0, WATCH_LIST_MAX);
  } catch (err) {
    console.warn('[nova] unreadable saved watch list', err);
    return EMPTY;
  }
}

/** Forget the list saved before the hot list (after it was starred, or when the operator says so). */
export function forgetSavedWatchList(): void {
  try {
    storage()?.removeItem(WATCH_LIST_STORAGE_KEY);
  } catch (err) {
    console.warn('[nova] could not forget the saved watch list', err);
  }
  notify();
}

let sampleList: readonly string[] = EMPTY;
/** Writes in flight: shown at once, dropped when the backend answers (its view is then the truth). */
const pending = new Map<string, 'add' | 'remove'>();
const listeners = new Set<() => void>();
let cache: { view: unknown; version: number; list: readonly string[] } | null = null;
let version = 0;

function notify(): void {
  version += 1;
  listeners.forEach(fn => fn());
}

function current(): readonly string[] {
  if (isSampleView()) return sampleList;
  const view = getHotListState().view;
  if (cache && cache.view === view && cache.version === version) return cache.list;
  const base = view ? view.entries.map(e => e.symbol) : [];
  let list = base.filter(s => pending.get(s) !== 'remove');
  for (const [s, op] of pending) if (op === 'add' && !list.includes(s)) list = [s, ...list];
  cache = { view, version, list };
  return list;
}

async function send(symbol: string, op: 'add' | 'remove'): Promise<void> {
  pending.set(symbol, op);
  notify();
  const refused = op === 'add' ? await hotListActions.star(symbol) : await hotListActions.unstar(symbol);
  pending.delete(symbol);
  notify();
  if (!refused) return;
  console.warn('[nova] the hot list refused', op, symbol, refused);
  alertApp({
    title: op === 'add' ? `${symbol} is not on today's hot list` : `${symbol} is still on today's hot list`,
    message: refused,
    tone: 'warning',
  }).catch(err => console.warn('[nova] could not show the hot list refusal', err));
}

export function getWatchList(): readonly string[] {
  return current();
}

export function isWatched(symbol: string): boolean {
  const s = normalizeWatchSymbol(symbol);
  return s !== null && current().includes(s);
}

/** Stars `symbol` on today's hot list; false when it is not a ticker. */
export function addToWatchList(symbol: string): boolean {
  const s = normalizeWatchSymbol(symbol);
  if (!s) return false;
  if (isSampleView()) {
    if (!sampleList.includes(s)) {
      sampleList = [s, ...sampleList];
      notify();
    }
    return true;
  }
  if (!current().includes(s)) void send(s, 'add');
  return true;
}

export function removeFromWatchList(symbol: string): void {
  const s = normalizeWatchSymbol(symbol);
  if (!s) return;
  if (isSampleView()) {
    if (sampleList.includes(s)) {
      sampleList = sampleList.filter(x => x !== s);
      notify();
    }
    return;
  }
  if (current().includes(s)) void send(s, 'remove');
}

/** Flips `symbol` on or off the list; returns whether it is listed afterwards. */
export function toggleWatchList(symbol: string): boolean {
  if (isWatched(symbol)) {
    removeFromWatchList(symbol);
    return false;
  }
  return addToWatchList(symbol);
}

/** Changes to the list: the hot list's (polled while anything listens) and this window's writes. */
export function subscribeWatchList(fn: () => void): () => void {
  listeners.add(fn);
  const stop = isSampleView() ? () => {} : subscribeHotList(fn);
  return () => {
    listeners.delete(fn);
    stop();
  };
}

export function useWatchList(): readonly string[] {
  return useSyncExternalStore(subscribeWatchList, current, current);
}

/** How ``symbol`` is on the list: your ★ (`star`, a star still being saved included), an auto ☆ (`auto`),
 * or null when it is not listed. The sample desk's list is all stars. */
export function watchHow(symbol: string): 'star' | 'auto' | null {
  const s = normalizeWatchSymbol(symbol);
  if (s === null || !current().includes(s)) return null;
  if (isSampleView() || pending.get(s) === 'add') return 'star';
  return getHotListState().view?.entries.find(e => e.symbol === s)?.how ?? 'star';
}

export function useWatchHow(symbol: string): 'star' | 'auto' | null {
  return useSyncExternalStore(subscribeWatchList, () => watchHow(symbol), () => null);
}

export function useIsWatched(symbol: string): boolean {
  return useSyncExternalStore(
    subscribeWatchList,
    () => isWatched(symbol),
    () => false,
  );
}

/** Test-only: forget the sample list, the writes in flight and the hot list's copy. */
export function resetWatchListForTests(): void {
  sampleList = EMPTY;
  pending.clear();
  cache = null;
  resetHotListForTests();
  notify();
}
