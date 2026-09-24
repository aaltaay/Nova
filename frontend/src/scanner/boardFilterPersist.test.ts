/**
 * @vitest-environment jsdom
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { SCANNER_BOARD_FILTERS_STORAGE_KEY, SCANNER_SAVED_CUSTOM, SCANNER_SAVED_NONE } from '../constantGroups/scanner_board';
import { PREF_SCHEMA_VERSION } from '../utils/prefStore';
import {
  parseBoardFilterState,
  readBoardFilterState,
  removeSavedSet,
  upsertSavedSet,
  writeBoardFilterState,
} from './boardFilterPersist';
import { useBoardFilters } from './useBoardFilters';

afterEach(() => {
  localStorage.removeItem(SCANNER_BOARD_FILTERS_STORAGE_KEY);
});

describe('boardFilterPersist', () => {
  it('round-trips active chips and named sets under the versioned envelope', () => {
    writeBoardFilterState({ active: ['gap', 'news'], sets: [{ name: 'Low-float runners', chips: ['gap', 'float'] }] });
    const raw = JSON.parse(localStorage.getItem(SCANNER_BOARD_FILTERS_STORAGE_KEY) ?? '{}');
    expect(raw.schema_version).toBe(PREF_SCHEMA_VERSION);
    expect(readBoardFilterState()).toEqual({
      active: ['gap', 'news'],
      sets: [{ name: 'Low-float runners', chips: ['gap', 'float'] }],
    });
  });

  it('falls back to empty on an unknown schema_version or garbage', () => {
    localStorage.setItem(SCANNER_BOARD_FILTERS_STORAGE_KEY, JSON.stringify({ schema_version: 42, value: { active: ['gap'] } }));
    expect(readBoardFilterState()).toEqual({ active: [], sets: [] });
    localStorage.setItem(SCANNER_BOARD_FILTERS_STORAGE_KEY, 'nope');
    expect(readBoardFilterState()).toEqual({ active: [], sets: [] });
  });

  it('drops unknown chip ids, blank names and duplicates while parsing', () => {
    expect(parseBoardFilterState({
      active: ['gap', 'bogus', 'gap'],
      sets: [
        { name: ' A ', chips: ['news', 'x'] },
        { name: 'A', chips: ['gap'] },
        { name: '', chips: ['gap'] },
        { name: 'B', chips: 'nope' },
      ],
    })).toEqual({ active: ['gap'], sets: [{ name: 'A', chips: ['news'] }] });
    expect(parseBoardFilterState('x')).toBeNull();
  });

  it('upserts by name and forgets by name', () => {
    const one = upsertSavedSet([], 'Runners', ['gap']);
    const two = upsertSavedSet(one, 'Runners', ['gap', 'float']);
    expect(two).toEqual([{ name: 'Runners', chips: ['gap', 'float'] }]);
    expect(upsertSavedSet(two, '  ', ['news'])).toEqual(two);
    expect(removeSavedSet(two, 'Runners')).toEqual([]);
  });
});

describe('useBoardFilters', () => {
  it('toggles, names the active set, saves and applies sets, and persists each step', () => {
    const { result } = renderHook(() => useBoardFilters());
    expect(result.current.activeSetName).toBe(SCANNER_SAVED_NONE);

    act(() => result.current.toggle('gap'));
    act(() => result.current.toggle('float'));
    expect([...result.current.active]).toEqual(['gap', 'float']);
    expect(result.current.activeSetName).toBe(SCANNER_SAVED_CUSTOM);
    expect(readBoardFilterState().active).toEqual(['gap', 'float']);

    act(() => result.current.saveCurrentAs('Low-float runners'));
    expect(result.current.activeSetName).toBe('Low-float runners');
    expect(readBoardFilterState().sets).toEqual([{ name: 'Low-float runners', chips: ['gap', 'float'] }]);

    act(() => result.current.clear());
    expect(result.current.active.size).toBe(0);
    act(() => result.current.applySet('Low-float runners'));
    expect([...result.current.active]).toEqual(['gap', 'float']);

    // Halted filters every board now (#487): it is stored like any other chip.
    act(() => result.current.toggle('halted'));
    expect([...result.current.active]).toEqual(['gap', 'float', 'halted']);
    expect(readBoardFilterState().active).toEqual(['gap', 'float', 'halted']);
    act(() => result.current.toggle('halted'));
    expect(result.current.activeSetName).toBe('Low-float runners');

    act(() => result.current.forgetSet('Low-float runners'));
    expect(result.current.sets).toEqual([]);
    expect(result.current.activeSetName).toBe(SCANNER_SAVED_CUSTOM);
  });

  it('filters rows with the active chips', () => {
    const { result } = renderHook(() => useBoardFilters());
    const rows = [
      { symbol: 'A', gap_percent: 0.5, float: null, rel_volume: null, has_news: true },
      { symbol: 'B', gap_percent: 0.01, float: null, rel_volume: null, has_news: true },
    ];
    expect(result.current.filterRows(rows)).toHaveLength(2);
    act(() => result.current.toggle('gap'));
    expect(result.current.filterRows(rows).map((r) => r.symbol)).toEqual(['A']);
  });
});
