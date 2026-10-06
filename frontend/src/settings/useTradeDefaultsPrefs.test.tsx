/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { defaultTradeDefaultsPrefs, tradeDefaultsStorageKey, writeTradeDefaultsPrefs } from './tradeDefaultsPrefs';
import { useTradeDefaultsPrefs } from './useTradeDefaultsPrefs';

describe('reactive per-venue defaults', () => {
  beforeEach(() => localStorage.clear());
  afterEach(cleanup);

  it('updates mounted readers after a same-window write and a venue switch', () => {
    const { result, rerender } = renderHook(({ venue }: { venue: DeskVenue | null }) => useTradeDefaultsPrefs(venue), {
      initialProps: { venue: 'paper' as DeskVenue | null },
    });
    act(() => { writeTradeDefaultsPrefs('paper', { ...defaultTradeDefaultsPrefs(), quantity: 7, tif: 'GTC' }); });
    expect(result.current).toMatchObject({ quantity: 7, tif: 'GTC' });
    rerender({ venue: 'live' });
    expect(result.current).toMatchObject({ quantity: 100, tif: 'DAY', protectiveLegs: false });
    rerender({ venue: 'paper' });
    expect(result.current.quantity).toBe(7);
  });

  it('updates on another window storage event, including clearing saved defaults', () => {
    const { result } = renderHook(() => useTradeDefaultsPrefs('sim'));
    act(() => {
      localStorage.setItem(tradeDefaultsStorageKey('sim'), JSON.stringify({
        schema_version: 2, venue: 'sim', prefs: { ...defaultTradeDefaultsPrefs(), quantity: 33 },
      }));
      window.dispatchEvent(new StorageEvent('storage', { key: tradeDefaultsStorageKey('sim'), storageArea: localStorage }));
    });
    expect(result.current.quantity).toBe(33);
    act(() => {
      localStorage.clear();
      window.dispatchEvent(new StorageEvent('storage', { key: null, storageArea: localStorage }));
    });
    expect(result.current.quantity).toBe(100);
  });
});
