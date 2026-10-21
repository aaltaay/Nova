/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { AHEAD_PREFS_KEY } from './aheadConstants';
import {
  AHEAD_DEFAULT_PREFS,
  parseAheadPrefs,
  readAheadPrefs,
  reloadAheadPrefsForTesting,
  setAheadPrefs,
  useAheadPrefs,
} from './aheadPrefs';

describe("Ahead's switch, scope and earned switch", () => {
  beforeEach(() => {
    localStorage.clear();
    reloadAheadPrefsForTesting();
  });

  it('starts off, on All, and hiding what has not earned it', () => {
    expect(readAheadPrefs()).toEqual({ shown: false, scope: 'all', unearned: false });
    expect(AHEAD_DEFAULT_PREFS.shown).toBe(false);
  });

  it('keeps a change in a versioned envelope', () => {
    setAheadPrefs({ shown: true, scope: 'flat_top' });
    const stored = JSON.parse(localStorage.getItem(AHEAD_PREFS_KEY) ?? 'null');
    expect(stored).toEqual({ schema_version: 1, value: { shown: true, scope: 'flat_top', unearned: false } });
    reloadAheadPrefsForTesting();
    expect(readAheadPrefs().scope).toBe('flat_top');
  });

  it("follows another window's change through the storage event", () => {
    const { result } = renderHook(() => useAheadPrefs());
    expect(result.current.shown).toBe(false);
    localStorage.setItem(AHEAD_PREFS_KEY, JSON.stringify({ schema_version: 1, value: { shown: true, scope: 'lines', unearned: true } }));
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: AHEAD_PREFS_KEY }));
    });
    expect(result.current).toEqual({ shown: true, scope: 'lines', unearned: true });
  });

  it('falls back field by field, and refuses an unknown envelope version', () => {
    expect(parseAheadPrefs({ shown: 'yes', scope: 'everything', unearned: true })).toEqual({
      shown: false, scope: 'all', unearned: true,
    });
    expect(parseAheadPrefs(null)).toBeNull();
    localStorage.setItem(AHEAD_PREFS_KEY, JSON.stringify({ schema_version: 9, value: { shown: true } }));
    reloadAheadPrefsForTesting();
    expect(readAheadPrefs().shown).toBe(false);
  });
});
