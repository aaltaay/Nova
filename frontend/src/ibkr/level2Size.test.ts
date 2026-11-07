/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { L2_SIZE_STORAGE_KEY } from '../constants';
import {
  parseLevel2Size,
  readLevel2Size,
  reloadLevel2SizeForTesting,
  setLevel2Size,
  useLevel2Size,
} from './level2Size';

describe("the Level 2 pane's size", () => {
  beforeEach(() => {
    localStorage.clear();
    reloadLevel2SizeForTesting();
  });

  it('starts large (mockup v1 B) and reads only the three sizes', () => {
    expect(readLevel2Size()).toBe('large');
    expect(parseLevel2Size('small')).toBe('small');
    expect(parseLevel2Size('huge')).toBeNull();
    expect(parseLevel2Size(2)).toBeNull();
  });

  it('keeps a change in a versioned envelope and reads it back as a fresh window would', () => {
    setLevel2Size('medium');
    expect(JSON.parse(localStorage.getItem(L2_SIZE_STORAGE_KEY) ?? 'null'))
      .toEqual({ schema_version: 1, value: 'medium' });
    reloadLevel2SizeForTesting();
    expect(readLevel2Size()).toBe('medium');
  });

  it('falls back to large on an unknown stored value', () => {
    localStorage.setItem(L2_SIZE_STORAGE_KEY, JSON.stringify({ schema_version: 1, value: 'giant' }));
    reloadLevel2SizeForTesting();
    expect(readLevel2Size()).toBe('large');
  });

  it("follows another window's change through the storage event", () => {
    const { result } = renderHook(() => useLevel2Size());
    expect(result.current).toBe('large');
    localStorage.setItem(L2_SIZE_STORAGE_KEY, JSON.stringify({ schema_version: 1, value: 'small' }));
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: L2_SIZE_STORAGE_KEY }));
    });
    expect(result.current).toBe('small');
  });
});
