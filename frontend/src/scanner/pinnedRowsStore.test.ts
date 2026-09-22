import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  _resetPinnedRowsForTests,
  getPinnedRows,
  isRowPinned,
  pinFirst,
  subscribePinnedRows,
  togglePinnedRow,
} from './pinnedRowsStore';

afterEach(() => {
  _resetPinnedRowsForTests();
});

describe('pinnedRowsStore', () => {
  it('toggles a pin (case-insensitive) and notifies subscribers', () => {
    const listener = vi.fn();
    const off = subscribePinnedRows(listener);
    togglePinnedRow(' grml ');
    expect(isRowPinned('GRML')).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
    togglePinnedRow('GRML');
    expect(isRowPinned('grml')).toBe(false);
    off();
    togglePinnedRow('GRML');
    expect(listener).toHaveBeenCalledTimes(2);
    expect(getPinnedRows().has('GRML')).toBe(true);
  });

  it('pinFirst leads with pinned rows in their current order and keeps the rest in order', () => {
    const rows = [{ symbol: 'AAA' }, { symbol: 'BBB' }, { symbol: 'CCC' }, { symbol: 'DDD' }];
    expect(pinFirst(rows, new Set()).map((r) => r.symbol)).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
    expect(pinFirst(rows, new Set(['DDD', 'BBB'])).map((r) => r.symbol)).toEqual(['BBB', 'DDD', 'AAA', 'CCC']);
    expect(pinFirst(rows, new Set(['ZZZ'])).map((r) => r.symbol)).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
  });

  it('ignores a blank symbol', () => {
    togglePinnedRow('   ');
    expect(getPinnedRows().size).toBe(0);
  });
});
