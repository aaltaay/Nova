/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WATCH_LIST_SCHEMA_VERSION, WATCH_LIST_STORAGE_KEY } from './watchListConstants';
import {
  addToWatchList,
  getWatchList,
  isWatched,
  normalizeWatchSymbol,
  readWatchList,
  removeFromWatchList,
  resetWatchListForTests,
  subscribeWatchList,
  toggleWatchList,
} from './watchListStore';

function stored(): unknown {
  return JSON.parse(localStorage.getItem(WATCH_LIST_STORAGE_KEY) ?? 'null');
}

describe('watchListStore', () => {
  beforeEach(() => {
    localStorage.clear();
    resetWatchListForTests();
  });
  afterEach(() => {
    localStorage.clear();
    resetWatchListForTests();
    vi.restoreAllMocks();
  });

  it('adds newest first, upper-cased, once, and persists the versioned shape', () => {
    expect(addToWatchList(' grml ')).toBe(true);
    expect(addToWatchList('AAPL')).toBe(true);
    expect(addToWatchList('grml')).toBe(true);
    expect(getWatchList()).toEqual(['AAPL', 'GRML']);
    expect(stored()).toEqual({ schema_version: WATCH_LIST_SCHEMA_VERSION, symbols: ['AAPL', 'GRML'] });
    expect(isWatched('grml')).toBe(true);
  });

  it('refuses text that cannot be a ticker', () => {
    expect(addToWatchList('')).toBe(false);
    expect(addToWatchList('not a ticker')).toBe(false);
    expect(addToWatchList('$$$')).toBe(false);
    expect(getWatchList()).toEqual([]);
    expect(normalizeWatchSymbol('brk/b')).toBe('BRK/B');
    expect(normalizeWatchSymbol('brk.b')).toBe('BRK.B');
  });

  it('removes and toggles, and tells subscribers', () => {
    const listener = vi.fn();
    const off = subscribeWatchList(listener);
    expect(toggleWatchList('XYZ')).toBe(true);
    expect(toggleWatchList('XYZ')).toBe(false);
    addToWatchList('ABC');
    removeFromWatchList('abc');
    expect(getWatchList()).toEqual([]);
    expect(listener).toHaveBeenCalledTimes(4);
    off();
  });

  it('ignores a payload with an unknown schema_version rather than guessing', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem(WATCH_LIST_STORAGE_KEY, JSON.stringify({ schema_version: 99, symbols: ['GRML'] }));
    expect(readWatchList()).toEqual([]);
  });

  it("follows another window's write through the storage event", () => {
    const listener = vi.fn();
    const off = subscribeWatchList(listener);
    localStorage.setItem(
      WATCH_LIST_STORAGE_KEY,
      JSON.stringify({ schema_version: WATCH_LIST_SCHEMA_VERSION, symbols: ['ONCO'] }),
    );
    window.dispatchEvent(new StorageEvent('storage', { key: WATCH_LIST_STORAGE_KEY }));
    expect(getWatchList()).toEqual(['ONCO']);
    expect(listener).toHaveBeenCalled();
    off();
  });

  it("the sample desk keeps its own list in memory: it never shows or changes the operator's (#449)", () => {
    addToWatchList('GRML');
    window.history.replaceState({}, '', '/?view=sample');
    try {
      expect(getWatchList()).toEqual([]);
      expect(toggleWatchList('SMPL')).toBe(true);
      expect(getWatchList()).toEqual(['SMPL']);
      expect(isWatched('GRML')).toBe(false);
    } finally {
      window.history.replaceState({}, '', '/');
    }
    expect(getWatchList()).toEqual(['GRML']);
    expect(stored()).toEqual({ schema_version: WATCH_LIST_SCHEMA_VERSION, symbols: ['GRML'] });
  });
});
