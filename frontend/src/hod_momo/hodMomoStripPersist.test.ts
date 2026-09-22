/**
 * @vitest-environment jsdom
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useHodMomoDockState } from './HodMomoContext';
import {
  HOD_MOMO_STRIP_DEFAULT_ROWS,
  HOD_MOMO_STRIP_MAX_ROWS,
  HOD_MOMO_STRIP_MIN_ROWS,
  HOD_MOMO_STRIP_ROW_PX,
  HOD_MOMO_STRIP_SCHEMA_VERSION,
  HOD_MOMO_STRIP_STORAGE_KEY,
} from './hodMomoStripConstants';
import {
  clampStripRows,
  readStripLayout,
  snapStripRows,
  stripMaxRowsFor,
  stripRowsToPx,
  writeStripLayout,
} from './hodMomoStripPersist';

afterEach(() => {
  localStorage.removeItem(HOD_MOMO_STRIP_STORAGE_KEY);
  vi.restoreAllMocks();
});

const stream = { alerts: [], totalToday: 0, connected: true };

describe('hodMomoStripPersist', () => {
  it('defaults when nothing is stored', () => {
    expect(readStripLayout()).toEqual({ rows: HOD_MOMO_STRIP_DEFAULT_ROWS, folded: false });
  });

  it('round-trips rows + folded under a versioned blob', () => {
    writeStripLayout({ rows: 7, folded: true });
    const raw = JSON.parse(localStorage.getItem(HOD_MOMO_STRIP_STORAGE_KEY) ?? '{}');
    expect(raw.schema_version).toBe(HOD_MOMO_STRIP_SCHEMA_VERSION);
    expect(readStripLayout()).toEqual({ rows: 7, folded: true });
  });

  it('refuses an unknown schema_version loudly and falls back to defaults', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem(HOD_MOMO_STRIP_STORAGE_KEY, JSON.stringify({ schema_version: 99, rows: 9 }));
    expect(readStripLayout()).toEqual({ rows: HOD_MOMO_STRIP_DEFAULT_ROWS, folded: false });
    expect(warn).toHaveBeenCalledOnce();
  });

  it('ignores garbage', () => {
    localStorage.setItem(HOD_MOMO_STRIP_STORAGE_KEY, '{not json');
    expect(readStripLayout().rows).toBe(HOD_MOMO_STRIP_DEFAULT_ROWS);
  });

  it('clamps to whole rows between the floor and the ceiling', () => {
    expect(clampStripRows(0)).toBe(HOD_MOMO_STRIP_MIN_ROWS);
    expect(clampStripRows(3.4)).toBe(3);
    expect(clampStripRows(3.6)).toBe(4);
    expect(clampStripRows(9999)).toBe(HOD_MOMO_STRIP_MAX_ROWS);
    expect(clampStripRows(20, 12)).toBe(12);
    expect(clampStripRows(Number.NaN)).toBe(HOD_MOMO_STRIP_DEFAULT_ROWS);
  });

  it('caps the live ceiling at 40% of the content column', () => {
    // 900px * 0.4 = 360px / 22px = 16 rows
    expect(stripMaxRowsFor(900)).toBe(16);
    expect(stripMaxRowsFor(0)).toBe(HOD_MOMO_STRIP_MAX_ROWS);
    expect(stripMaxRowsFor(30)).toBe(HOD_MOMO_STRIP_MIN_ROWS);
  });

  it('snaps a dragged pixel height to whole rows', () => {
    expect(snapStripRows(4 * HOD_MOMO_STRIP_ROW_PX + 8, 16)).toBe(4);
    expect(snapStripRows(4 * HOD_MOMO_STRIP_ROW_PX + 12, 16)).toBe(5);
    expect(snapStripRows(2, 16)).toBe(HOD_MOMO_STRIP_MIN_ROWS);
    expect(snapStripRows(99_999, 16)).toBe(16);
    expect(stripRowsToPx(3)).toBe(3 * HOD_MOMO_STRIP_ROW_PX);
  });
});

describe('useHodMomoDockState (strip layout)', () => {
  it('persists rows and folded through the context setters', () => {
    const { result } = renderHook(() => useHodMomoDockState(stream));
    expect(result.current.rows).toBe(HOD_MOMO_STRIP_DEFAULT_ROWS);
    expect(result.current.collapsed).toBe(false);

    act(() => result.current.setRows(6));
    expect(result.current.rows).toBe(6);
    expect(readStripLayout()).toEqual({ rows: 6, folded: false });

    act(() => result.current.toggleCollapsed());
    expect(result.current.collapsed).toBe(true);
    expect(readStripLayout()).toEqual({ rows: 6, folded: true });

    act(() => result.current.focusDock('running_up'));
    expect(result.current.collapsed).toBe(false);
    expect(result.current.dockMode).toBe('running_up');
    expect(readStripLayout().folded).toBe(false);
  });

  it('restores a stored layout on mount', () => {
    writeStripLayout({ rows: 9, folded: true });
    const { result } = renderHook(() => useHodMomoDockState(stream));
    expect(result.current.rows).toBe(9);
    expect(result.current.collapsed).toBe(true);
  });
});
