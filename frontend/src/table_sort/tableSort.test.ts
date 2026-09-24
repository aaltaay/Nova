import { describe, expect, it } from 'vitest';
import { firstSortDir, nextTableSort, parseTableSort, sortTableRows, type SortColumns } from './tableSort';

interface Row { sym: string; pct: number | null; note?: string; on?: boolean }

const ROWS: Row[] = [
  { sym: 'GCTK', pct: 25.6, note: 'b' },
  { sym: 'APUS', pct: 135.8, note: '' },
  { sym: 'PFSA', pct: null, note: 'a' },
  { sym: 'aifu', pct: 12.6, note: 'A10' },
  { sym: 'SRZN', pct: 25.6, note: 'A2' },
];

const COLS: SortColumns<Row> = {
  sym: r => r.sym,
  pct: r => r.pct,
  note: r => r.note,
  on: { value: r => r.on, first: 'asc' },
};

const syms = (rows: Row[]) => rows.map(r => r.sym);

describe('nextTableSort', () => {
  it('starts a new column at its first direction, flips it, then clears', () => {
    const one = nextTableSort(null, 'pct', 'desc');
    expect(one).toEqual({ key: 'pct', dir: 'desc' });
    const two = nextTableSort(one, 'pct', 'desc');
    expect(two).toEqual({ key: 'pct', dir: 'asc' });
    expect(nextTableSort(two, 'pct', 'desc')).toBeNull();
  });

  it('a different column starts over at its own first direction', () => {
    expect(nextTableSort({ key: 'pct', dir: 'asc' }, 'sym', 'asc')).toEqual({ key: 'sym', dir: 'asc' });
  });
});

describe('firstSortDir', () => {
  it('sorts text A to Z and numbers highest first unless the column says otherwise', () => {
    expect(firstSortDir(COLS.sym, ROWS)).toBe('asc');
    expect(firstSortDir(COLS.pct, ROWS)).toBe('desc');
    expect(firstSortDir(COLS.on, ROWS)).toBe('asc');
    expect(firstSortDir(undefined, ROWS)).toBe('desc');
  });

  it('reads the first value that is there', () => {
    expect(firstSortDir<Row>(r => r.pct, [{ sym: 'X', pct: null }, { sym: 'Y', pct: 3 }])).toBe('desc');
  });
});

describe('sortTableRows', () => {
  it('returns the rows as given with no sort or an unknown column', () => {
    expect(sortTableRows(ROWS, null, COLS)).toBe(ROWS);
    expect(sortTableRows(ROWS, { key: 'gone', dir: 'asc' }, COLS)).toBe(ROWS);
  });

  it('sorts numbers highest first and keeps ties in the table order', () => {
    expect(syms(sortTableRows(ROWS, { key: 'pct', dir: 'desc' }, COLS))).toEqual(['APUS', 'GCTK', 'SRZN', 'aifu', 'PFSA']);
  });

  it('puts a missing value last in both directions', () => {
    expect(syms(sortTableRows(ROWS, { key: 'pct', dir: 'asc' }, COLS))).toEqual(['aifu', 'GCTK', 'SRZN', 'APUS', 'PFSA']);
  });

  it('sorts text case-blind with digits read as numbers, and empty text as missing', () => {
    expect(syms(sortTableRows(ROWS, { key: 'sym', dir: 'asc' }, COLS))).toEqual(['aifu', 'APUS', 'GCTK', 'PFSA', 'SRZN']);
    expect(syms(sortTableRows(ROWS, { key: 'note', dir: 'asc' }, COLS))).toEqual(['PFSA', 'SRZN', 'aifu', 'GCTK', 'APUS']);
  });

  it('reads NaN as missing and true above false when highest first', () => {
    const rows: Row[] = [
      { sym: 'A', pct: Number.NaN, on: false },
      { sym: 'B', pct: 1, on: true },
      { sym: 'C', pct: 2 },
    ];
    expect(syms(sortTableRows(rows, { key: 'pct', dir: 'desc' }, COLS))).toEqual(['C', 'B', 'A']);
    expect(syms(sortTableRows(rows, { key: 'on', dir: 'desc' }, COLS))).toEqual(['B', 'A', 'C']);
  });
});

describe('parseTableSort', () => {
  it('keeps a well-formed sort and refuses anything else', () => {
    expect(parseTableSort({ key: 'pct', dir: 'desc' })).toEqual({ key: 'pct', dir: 'desc' });
    expect(parseTableSort({ key: 'pct', dir: 'up' })).toBeNull();
    expect(parseTableSort({ key: '', dir: 'asc' })).toBeNull();
    expect(parseTableSort('pct')).toBeNull();
    expect(parseTableSort(null)).toBeNull();
  });
});
