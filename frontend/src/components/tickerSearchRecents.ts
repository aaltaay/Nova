/**
 * Recently opened symbols for the bar search, newest first: every search
 * look-up, plus every Trader tab opened while the desk runs.
 *
 * Owner: this module (read + write) under GLOBAL_BAR_SEARCH_RECENTS_STORAGE_KEY.
 * Invalidation: schema bump -- a payload with an unknown `schema_version` is
 * ignored, never guessed at (persisted-state.mdc). Storage that throws
 * (private window, quota) leaves the list in memory for this session only.
 * The sample desk (#449) keeps its own list, in memory: its invented tickers
 * never join the operator's recents, saved or in this page.
 */
import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import {
  GLOBAL_BAR_SEARCH_RECENTS_MAX,
  GLOBAL_BAR_SEARCH_RECENTS_SCHEMA_VERSION,
  GLOBAL_BAR_SEARCH_RECENTS_STORAGE_KEY,
} from '../constantGroups/global_bar';
import { isSampleView } from '../sample_data/sampleNav';

const EMPTY: readonly string[] = [];

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readRecents(): readonly string[] {
  const store = storage();
  if (!store) return EMPTY;
  try {
    const raw = store.getItem(GLOBAL_BAR_SEARCH_RECENTS_STORAGE_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as { schema_version?: unknown; symbols?: unknown };
    if (parsed.schema_version !== GLOBAL_BAR_SEARCH_RECENTS_SCHEMA_VERSION) {
      console.warn('[nova] ignoring recent symbols with unknown schema_version', parsed.schema_version);
      return EMPTY;
    }
    if (!Array.isArray(parsed.symbols)) return EMPTY;
    return parsed.symbols
      .filter((s): s is string => typeof s === 'string' && s.length > 0)
      .slice(0, GLOBAL_BAR_SEARCH_RECENTS_MAX);
  } catch (err) {
    console.warn('[nova] unreadable recent symbols', err);
    return EMPTY;
  }
}

/** Pure: `symbols` moved to the front (in the order given), de-duplicated, capped. */
export function withRecent(list: readonly string[], symbols: readonly string[]): readonly string[] {
  const front = symbols.map((s) => s.trim().toUpperCase()).filter(Boolean).reverse();
  if (!front.length) return list;
  const next = [...new Set([...front, ...list])];
  return next.slice(0, GLOBAL_BAR_SEARCH_RECENTS_MAX);
}

let recents: readonly string[] | null = null;
let sampleRecents: readonly string[] = EMPTY;
const listeners = new Set<() => void>();

function current(): readonly string[] {
  if (isSampleView()) return sampleRecents;
  if (recents === null) recents = readRecents();
  return recents;
}

function write(next: readonly string[]) {
  if (isSampleView()) {
    if (next === sampleRecents) return;
    sampleRecents = next;
    listeners.forEach((fn) => fn());
    return;
  }
  if (next === recents) return;
  recents = next;
  try {
    storage()?.setItem(
      GLOBAL_BAR_SEARCH_RECENTS_STORAGE_KEY,
      JSON.stringify({ schema_version: GLOBAL_BAR_SEARCH_RECENTS_SCHEMA_VERSION, symbols: next }),
    );
  } catch (err) {
    console.warn('[nova] could not save recent symbols', err);
  }
  listeners.forEach((fn) => fn());
}

export function pushRecent(...symbols: string[]) {
  write(withRecent(current(), symbols));
}

export function removeRecent(symbol: string) {
  write(current().filter((s) => s !== symbol));
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/**
 * The recent list, kept current across every mounted search. Trader tabs that
 * appear after mount are remembered too (the tabs restored at start are not
 * "recent" -- they are already offered as tabs).
 */
export function useTickerRecents(tabs: readonly string[]) {
  const list = useSyncExternalStore(subscribe, current, current);
  const seenTabs = useRef<Set<string> | null>(null);
  useEffect(() => {
    const now = new Set(tabs.map((t) => t.trim().toUpperCase()).filter(Boolean));
    const before = seenTabs.current;
    seenTabs.current = now;
    if (!before) return;
    const opened = [...now].filter((s) => !before.has(s));
    if (opened.length) pushRecent(...opened);
  }, [tabs]);
  const remember = useCallback((symbol: string) => pushRecent(symbol), []);
  const forget = useCallback((symbol: string) => removeRecent(symbol), []);
  return { recents: list, remember, forget };
}

export function resetRecentsForTests() {
  recents = null;
  sampleRecents = EMPTY;
  listeners.forEach((fn) => fn());
}
