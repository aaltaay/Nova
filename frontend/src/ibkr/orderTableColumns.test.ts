import { describe, expect, it } from 'vitest';
import {
  CLOSED_COLUMN_META,
  DEFAULT_CLOSED_ORDER_COLUMNS,
  DEFAULT_WORKING_ORDER_COLUMNS,
  WORKING_COLUMN_META,
  moveColumnOrder,
  normalizeColumnOrder,
  parseColumnStore,
  visibleWorkingColumns,
} from './orderTableColumns';

describe('orderTableColumns', () => {
  it('defaults working columns time → … → order_id', () => {
    expect(DEFAULT_WORKING_ORDER_COLUMNS).toEqual([
      'time',
      'session',
      'type',
      'symbol',
      'qty',
      'status',
      'filled',
      'remaining',
      'limit',
      'stop',
      'avg_fill',
      'order_id',
    ]);
  });

  it('defaults closed columns to Time Filled first, then mirror open (time, status after qty)', () => {
    expect(DEFAULT_CLOSED_ORDER_COLUMNS).toEqual([
      'filled_at',
      'time',
      'type',
      'symbol',
      'qty',
      'status',
      'filled',
      'limit',
      'avg_fill',
      'order_id',
    ]);
  });

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
    expect(vis).toContain('filled');
  });

  it('documents Filled / Remaining / Average fill for active fill progress', () => {
    expect(WORKING_COLUMN_META.filled.label).toBe('Filled');
    expect(WORKING_COLUMN_META.filled.title).toMatch(/filled so far/i);
    expect(WORKING_COLUMN_META.remaining.title).toMatch(/Fill now/i);
    expect(WORKING_COLUMN_META.avg_fill.title).toMatch(/Average fill/i);
    expect(CLOSED_COLUMN_META.filled.title).toMatch(/partial cancel/i);
    expect(CLOSED_COLUMN_META.filled_at.label).toBe('Time Filled');
    expect(CLOSED_COLUMN_META.filled_at.title).toMatch(/fill time/i);
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
