import { describe, expect, it } from 'vitest';
import { ACCOUNT_RANGE_STORAGE_KEY } from '../constantGroups/account_page';
import { isAccountRange, readAccountRangePref, writeAccountRangePref } from './accountRangePref';

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() { return map.size; },
    clear: () => map.clear(),
    getItem: (k) => map.get(k) ?? null,
    key: (i) => [...map.keys()][i] ?? null,
    removeItem: (k) => { map.delete(k); },
    setItem: (k, v) => { map.set(k, v); },
  };
}

describe('accountRangePref', () => {
  it('defaults to 1D, round-trips a written range under its schema version', () => {
    const storage = memoryStorage();
    expect(readAccountRangePref(storage)).toBe('1D');
    writeAccountRangePref('3M', storage);
    expect(JSON.parse(storage.getItem(ACCOUNT_RANGE_STORAGE_KEY)!)).toEqual({ schema_version: 1, range: '3M' });
    expect(readAccountRangePref(storage)).toBe('3M');
  });

  it('ignores an unknown schema, an unknown range and garbage rather than guessing', () => {
    const storage = memoryStorage();
    storage.setItem(ACCOUNT_RANGE_STORAGE_KEY, JSON.stringify({ schema_version: 2, range: '5D' }));
    expect(readAccountRangePref(storage)).toBe('1D');
    storage.setItem(ACCOUNT_RANGE_STORAGE_KEY, JSON.stringify({ schema_version: 1, range: '6M' }));
    expect(readAccountRangePref(storage)).toBe('1D');
    storage.setItem(ACCOUNT_RANGE_STORAGE_KEY, '{not json');
    expect(readAccountRangePref(storage)).toBe('1D');
    expect(readAccountRangePref(null)).toBe('1D');
  });

  it('guards the range union', () => {
    expect(isAccountRange('YTD')).toBe(true);
    expect(isAccountRange('1Y')).toBe(false);
    expect(isAccountRange(null)).toBe(false);
  });
});
