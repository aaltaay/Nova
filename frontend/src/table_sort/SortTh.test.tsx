/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TABLE_SORT_STORAGE_PREFIX } from '../constants';
import { SortTh } from './SortTh';
import { useTableSort } from './useTableSort';
import type { SortColumns } from './tableSort';

interface Row { sym: string; pct: number | null }

const ROWS: Row[] = [
  { sym: 'GCTK', pct: 25.6 },
  { sym: 'APUS', pct: 135.8 },
  { sym: 'PFSA', pct: null },
  { sym: 'AIFU', pct: 12.6 },
];

const COLS: SortColumns<Row> = { sym: r => r.sym, pct: r => r.pct };

function Table({ id = 'test-table' }: { id?: string | null }) {
  const { rows, sort, onSort } = useTableSort(id, ROWS, COLS);
  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <SortTh col="sym" sort={sort} onSort={onSort}>Symbol</SortTh>
          <SortTh col="pct" sort={sort} onSort={onSort} className="num">% Chg</SortTh>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => <tr key={r.sym}><td>{r.sym}</td></tr>)}
      </tbody>
    </table>
  );
}

const order = () => screen.getAllByRole('row').slice(1).map(r => r.textContent);
const header = (name: string) => screen.getByRole('columnheader', { name });

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('SortTh + useTableSort', () => {
  it('cycles highest first, lowest first, then the table order on a number column', () => {
    render(<Table />);
    expect(order()).toEqual(['GCTK', 'APUS', 'PFSA', 'AIFU']);
    act(() => fireEvent.click(header('% Chg')));
    expect(order()).toEqual(['APUS', 'GCTK', 'AIFU', 'PFSA']);
    expect(header('% Chg').getAttribute('aria-sort')).toBe('descending');
    act(() => fireEvent.click(header('% Chg')));
    expect(order()).toEqual(['AIFU', 'GCTK', 'APUS', 'PFSA']);
    expect(header('% Chg').getAttribute('aria-sort')).toBe('ascending');
    act(() => fireEvent.click(header('% Chg')));
    expect(order()).toEqual(['GCTK', 'APUS', 'PFSA', 'AIFU']);
    expect(header('% Chg').getAttribute('aria-sort')).toBe('none');
  });

  it('sorts text A to Z first, from the keyboard too', () => {
    render(<Table />);
    act(() => fireEvent.keyDown(header('Symbol'), { key: 'Enter' }));
    expect(order()).toEqual(['AIFU', 'APUS', 'GCTK', 'PFSA']);
    expect(header('Symbol').className).toBe('sortable-th');
    expect(header('% Chg').className).toBe('sortable-th num');
  });

  it('remembers the sort per table id and forgets it once cleared', () => {
    const { unmount } = render(<Table />);
    act(() => fireEvent.click(header('% Chg')));
    unmount();
    const key = `${TABLE_SORT_STORAGE_PREFIX}.test-table`;
    expect(localStorage.getItem(key)).toContain('"desc"');
    render(<Table />);
    expect(order()).toEqual(['APUS', 'GCTK', 'AIFU', 'PFSA']);
    act(() => fireEvent.click(header('% Chg')));
    act(() => fireEvent.click(header('% Chg')));
    expect(localStorage.getItem(key)).toBeNull();
  });

  it('keeps nothing with no table id', () => {
    render(<Table id={null} />);
    act(() => fireEvent.click(header('% Chg')));
    expect(localStorage.length).toBe(0);
  });
});
