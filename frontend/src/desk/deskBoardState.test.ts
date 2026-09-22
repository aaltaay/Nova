import { describe, expect, it } from 'vitest';
import { DESK_BOARD_STORAGE_KEY } from '../constantGroups/desk';
import {
  DESK_BOARD_DEFAULT_STATE,
  DESK_BOARD_STATE_VERSION,
  readDeskBoardState,
  writeDeskBoardState,
} from './deskBoardState';

function memoryStorage(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => { map.set(key, value); },
    dump: () => Object.fromEntries(map),
  };
}

describe('deskBoardState', () => {
  it('defaults to Gappers with no storage, an empty store, or an older shape', () => {
    expect(readDeskBoardState(null)).toEqual(DESK_BOARD_DEFAULT_STATE);
    expect(readDeskBoardState(memoryStorage())).toEqual(DESK_BOARD_DEFAULT_STATE);
    expect(readDeskBoardState(memoryStorage({ [DESK_BOARD_STORAGE_KEY]: JSON.stringify({ v: 0, list: 'losers' }) }))).toEqual(DESK_BOARD_DEFAULT_STATE);
    expect(readDeskBoardState(memoryStorage({ [DESK_BOARD_STORAGE_KEY]: '{not json' }))).toEqual(DESK_BOARD_DEFAULT_STATE);
    expect(readDeskBoardState(memoryStorage({ [DESK_BOARD_STORAGE_KEY]: JSON.stringify({ v: 1, list: '' }) })).list).toBe('gappers');
  });

  it('round-trips the picked list under the versioned key', () => {
    const store = memoryStorage();
    writeDeskBoardState({ v: DESK_BOARD_STATE_VERSION, list: 'losers' }, store);
    expect(JSON.parse(store.dump()[DESK_BOARD_STORAGE_KEY])).toEqual({ v: 1, list: 'losers' });
    expect(readDeskBoardState(store)).toEqual({ v: 1, list: 'losers' });
  });

  it('survives a storage that throws', () => {
    const throwing = {
      getItem: () => { throw new Error('private mode'); },
      setItem: () => { throw new Error('private mode'); },
    };
    expect(readDeskBoardState(throwing)).toEqual(DESK_BOARD_DEFAULT_STATE);
    expect(() => writeDeskBoardState({ v: 1, list: 'gainers' }, throwing)).not.toThrow();
  });
});
