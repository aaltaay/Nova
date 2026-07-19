import { describe, expect, it } from 'vitest';
import {
  DEFAULT_WORKING_ORDER_COLUMNS,
  moveColumnOrder,
  normalizeColumnOrder,
  parseColumnStore,
  visibleWorkingColumns,
} from './orderTableColumns';

describe('orderTableColumns', () => {
  it('normalizes saved order and appends new defaults', () => {
    const saved = ['symbol', 'qty', 'bogus', 'symbol', 'status'];
    const next = normalizeColumnOrder(saved, DEFAULT_WORKING_ORDER_COLUMNS);
    expect(next[0]).toBe('symbol');
    expect(next[1]).toBe('qty');
    expect(next).toContain('order_id');
    expect(next).not.toContain('bogus');
    expect(new Set(next).size).toBe(next.length);
    expect(next.length).toBe(DEFAULT_WORKING_ORDER_COLUMNS.length);
  });

  it('moves a column onto another', () => {
    const order = ['a', 'b', 'c', 'd'];
    expect(moveColumnOrder(order, 'a', 'c')).toEqual(['b', 'c', 'a', 'd']);
    expect(moveColumnOrder(order, 'd', 'a')).toEqual(['d', 'a', 'b', 'c']);
    expect(moveColumnOrder(order, 'a', 'a')).toBe(order);
  });

  it('hides compact-only columns for working table', () => {
    const vis = visibleWorkingColumns([...DEFAULT_WORKING_ORDER_COLUMNS], true);
    expect(vis).not.toContain('remaining');
    expect(vis).not.toContain('stop');
    expect(vis).not.toContain('session');
    expect(vis).toContain('symbol');
  });

  it('parses persisted store JSON', () => {
    const store = parseColumnStore(
      JSON.stringify({
        working: ['symbol', 'qty', 'status'],
        closed: ['time', 'symbol'],
      }),
    );
    expect(store.working[0]).toBe('symbol');
    expect(store.closed[0]).toBe('time');
    expect(store.positions[0]).toBe('symbol');
  });
});
