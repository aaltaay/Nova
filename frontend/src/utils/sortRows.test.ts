import { describe, expect, it } from 'vitest';
import type { SortConfig } from '../types/scanner';
import { sortedArray, toggleSort } from './sortRows';

const ROWS = [
  { symbol: 'GCTK', change_pct: 25.6, newest_headline_at: '2026-09-24T08:01:00Z' },
  { symbol: 'APUS', change_pct: 135.8, newest_headline_at: null },
  { symbol: 'PFSA', change_pct: 42.5, newest_headline_at: '2026-09-24T09:15:00Z' },
];

function click(current: SortConfig, key: string): SortConfig {
  let next = current;
  toggleSort(current, s => { next = s; }, key, ROWS);
  return next;
}

describe('toggleSort (scanner tables)', () => {
  it('sorts a number column highest first, then lowest first, then the list order', () => {
    const one = click({ key: '', dir: null }, 'change_pct');
    expect(one).toEqual({ key: 'change_pct', dir: 'desc' });
    expect(sortedArray(ROWS, one).map(r => r.symbol)).toEqual(['APUS', 'PFSA', 'GCTK']);
    const two = click(one, 'change_pct');
    expect(two).toEqual({ key: 'change_pct', dir: 'asc' });
    expect(click(two, 'change_pct')).toEqual({ key: '', dir: null });
  });

  it('sorts symbols A to Z first and the news time newest first', () => {
    expect(click({ key: '', dir: null }, 'symbol')).toEqual({ key: 'symbol', dir: 'asc' });
    const news = click({ key: 'symbol', dir: 'asc' }, 'newest_headline_at');
    expect(news).toEqual({ key: 'newest_headline_at', dir: 'desc' });
    expect(sortedArray(ROWS, news).map(r => r.symbol)).toEqual(['PFSA', 'GCTK', 'APUS']);
  });
});
