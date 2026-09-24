/**
 * The operator's watch list, newest first, shared by every window of the desk.
 *
 * Owner: this module (read + write) under WATCH_LIST_STORAGE_KEY as
 * `{schema_version: 1, symbols: string[]}`. Invalidation: schema bump -- a
 * payload with an unknown `schema_version` is ignored, never guessed at
 * (persisted-state.mdc). Another window's write arrives through the `storage`
 * event, so a pop-out and the main desk never disagree. Storage that throws
 * (private window, quota) keeps the list in memory for this session only.
 * The sample desk (#449) keeps a list of its own, in memory, starting empty:
 * it never shows the operator's list, and its picks never join it.
 */
import { useSyncExternalStore } from 'react';
import { isSampleView } from '../sample_data/sampleNav';
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

export function readWatchList(): readonly string[] {
  const store = storage();
  if (!store) return EMPTY;
  try {
    const raw = store.getItem(WATCH_LIST_STORAGE_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as { schema_version?: unknown; symbols?: unknown };
    if (parsed.schema_version !== WATCH_LIST_SCHEMA_VERSION) {
      console.warn('[nova] ignoring a watch list with unknown schema_version', parsed.schema_version);
      return EMPTY;
    }
    if (!Array.isArray(parsed.symbols)) return EMPTY;
    const symbols = parsed.symbols
      .map(s => (typeof s === 'string' ? normalizeWatchSymbol(s) : null))
      .filter((s): s is string => s !== null);
    return [...new Set(symbols)].slice(0, WATCH_LIST_MAX);
  } catch (err) {
    console.warn('[nova] unreadable watch list', err);
    return EMPTY;
  }
}

let list: readonly string[] | null = null;
let sampleList: readonly string[] = EMPTY;
let listening = false;
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach(fn => fn());
}

function onStorage(event: StorageEvent): void {
  if (event.key !== WATCH_LIST_STORAGE_KEY && event.key !== null) return;
  list = readWatchList();
  notify();
}

function current(): readonly string[] {
  if (isSampleView()) return sampleList;
  if (list === null) list = readWatchList();
  return list;
}

function write(next: readonly string[]): void {
  if (isSampleView()) {
    if (next === sampleList) return;
    sampleList = next;
    notify();
    return;
  }
  if (next === list) return;
  list = next;
  try {
    storage()?.setItem(
      WATCH_LIST_STORAGE_KEY,
      JSON.stringify({ schema_version: WATCH_LIST_SCHEMA_VERSION, symbols: next }),
    );
  } catch (err) {
    console.warn('[nova] could not save the watch list', err);
  }
  notify();
}

export function getWatchList(): readonly string[] {
  return current();
}

export function isWatched(symbol: string): boolean {
  const s = normalizeWatchSymbol(symbol);
  return s !== null && current().includes(s);
}

/** Adds `symbol` at the front; false when it is not a ticker. */
export function addToWatchList(symbol: string): boolean {
  const s = normalizeWatchSymbol(symbol);
  if (!s) return false;
  const now = current();
  if (!now.includes(s)) write([s, ...now].slice(0, WATCH_LIST_MAX));
  return true;
}

export function removeFromWatchList(symbol: string): void {
  const s = normalizeWatchSymbol(symbol);
  if (!s) return;
  const now = current();
  if (now.includes(s)) write(now.filter(x => x !== s));
}

/** Flips `symbol` on or off the list; returns whether it is watched afterwards. */
export function toggleWatchList(symbol: string): boolean {
  if (isWatched(symbol)) {
    removeFromWatchList(symbol);
    return false;
  }
  return addToWatchList(symbol);
}

export function subscribeWatchList(fn: () => void): () => void {
  listeners.add(fn);
  if (!listening && typeof window !== 'undefined') {
    window.addEventListener('storage', onStorage);
    listening = true;
  }
  return () => {
    listeners.delete(fn);
  };
}

export function useWatchList(): readonly string[] {
  return useSyncExternalStore(subscribeWatchList, current, current);
}

export function useIsWatched(symbol: string): boolean {
  return useSyncExternalStore(
    subscribeWatchList,
    () => isWatched(symbol),
    () => false,
  );
}

/** Test-only: forget the in-memory copy so the next read comes from storage. */
export function resetWatchListForTests(): void {
  list = null;
  sampleList = EMPTY;
  notify();
}
