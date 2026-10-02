/**
 * @vitest-environment jsdom
 *
 * The watch list is today's hot list (ADR 044): a Watch action stars or unstars on the hot list, shows at
 * once, and is undone -- in the backend's words -- when the hot list refuses it. The list this desk kept
 * before is only read, then forgotten. The sample desk keeps its own list.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fakeHotList } from '../hot_list/hotListFake';
import { WATCH_LIST_SCHEMA_VERSION, WATCH_LIST_STORAGE_KEY } from './watchListConstants';
import {
  addToWatchList,
  forgetSavedWatchList,
  getWatchList,
  isWatched,
  normalizeWatchSymbol,
  readSavedWatchList,
  removeFromWatchList,
  resetWatchListForTests,
  subscribeWatchList,
  toggleWatchList,
} from './watchListStore';

vi.mock('../hot_list', async () => (await import('../hot_list/hotListFake')).hotListFakeModule());
const alertApp = vi.hoisted(() => vi.fn(async () => undefined));
vi.mock('../ux/appDialogApi', () => ({ alertApp }));

async function settle() {
  for (let i = 0; i < 4; i += 1) await Promise.resolve();
}

describe('the watch list is today\'s hot list', () => {
  beforeEach(() => {
    localStorage.clear();
    fakeHotList.reset();
    resetWatchListForTests();
    alertApp.mockClear();
  });
  afterEach(() => {
    localStorage.clear();
    fakeHotList.reset();
    resetWatchListForTests();
    vi.restoreAllMocks();
  });

  it('stars newest first, upper-cased, once -- shown at once, then the hot list\'s own', async () => {
    expect(addToWatchList(' grml ')).toBe(true);
    expect(getWatchList()).toEqual(['GRML']);
    await settle();
    expect(addToWatchList('AAPL')).toBe(true);
    expect(addToWatchList('grml')).toBe(true);
    await settle();
    expect(getWatchList()).toEqual(['AAPL', 'GRML']);
    expect(fakeHotList.symbols()).toEqual(['AAPL', 'GRML']);
    expect(isWatched('grml')).toBe(true);
    // Nothing is kept in this desk any more.
    expect(localStorage.getItem(WATCH_LIST_STORAGE_KEY)).toBeNull();
  });

  it('reads the hot list as it is: a name the leaders rule put on is on the watch list too', () => {
    fakeHotList.set(['LGHL', 'AISP']);
    expect(getWatchList()).toEqual(['LGHL', 'AISP']);
  });

  it('refuses text that cannot be a ticker', () => {
    expect(addToWatchList('')).toBe(false);
    expect(addToWatchList('not a ticker')).toBe(false);
    expect(addToWatchList('$$$')).toBe(false);
    expect(getWatchList()).toEqual([]);
    expect(normalizeWatchSymbol('brk/b')).toBe('BRK/B');
    expect(normalizeWatchSymbol('brk.b')).toBe('BRK.B');
  });

  it('removes and toggles, and tells subscribers', async () => {
    const listener = vi.fn();
    const off = subscribeWatchList(listener);
    expect(toggleWatchList('XYZ')).toBe(true);
    await settle();
    expect(toggleWatchList('XYZ')).toBe(false);
    await settle();
    addToWatchList('ABC');
    await settle();
    removeFromWatchList('abc');
    await settle();
    expect(getWatchList()).toEqual([]);
    expect(listener).toHaveBeenCalled();
    off();
  });

  it('undoes a refused star and says why, in the backend\'s words', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    fakeHotList.refuseNext('Today\'s hot list is full (20): take one off first.');
    addToWatchList('MORE');
    expect(getWatchList()).toEqual(['MORE']);
    await settle();
    expect(getWatchList()).toEqual([]);
    expect(alertApp).toHaveBeenCalledWith(expect.objectContaining({
      title: 'MORE is not on today\'s hot list', message: 'Today\'s hot list is full (20): take one off first.',
    }));
  });

  it('reads the list saved before the hot list, ignores an unknown version, and forgets it', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem(WATCH_LIST_STORAGE_KEY, JSON.stringify({ schema_version: 99, symbols: ['GRML'] }));
    expect(readSavedWatchList()).toEqual([]);
    localStorage.setItem(WATCH_LIST_STORAGE_KEY,
      JSON.stringify({ schema_version: WATCH_LIST_SCHEMA_VERSION, symbols: ['grml', 'ONCO', 'GRML'] }));
    expect(readSavedWatchList()).toEqual(['GRML', 'ONCO']);
    forgetSavedWatchList();
    expect(localStorage.getItem(WATCH_LIST_STORAGE_KEY)).toBeNull();
    expect(readSavedWatchList()).toEqual([]);
  });

  it("the sample desk keeps its own list in memory: it never shows or changes the operator's (#449)", async () => {
    fakeHotList.set(['GRML']);
    window.history.replaceState({}, '', '/?view=sample');
    try {
      expect(getWatchList()).toEqual([]);
      expect(toggleWatchList('SMPL')).toBe(true);
      expect(getWatchList()).toEqual(['SMPL']);
      expect(isWatched('GRML')).toBe(false);
      await settle();
    } finally {
      window.history.replaceState({}, '', '/');
    }
    expect(getWatchList()).toEqual(['GRML']);
    expect(fakeHotList.symbols()).toEqual(['GRML']);
  });
});
