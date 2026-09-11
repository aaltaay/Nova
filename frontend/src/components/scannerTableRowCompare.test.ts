import { describe, expect, it, vi } from 'vitest';
import {
  scannerTableRowPropsEqual,
  type ScannerTableRowProps,
} from './ScannerTableRow';
import type { ScannerRow } from '../types/scanner';

function row(symbol: string): ScannerRow {
  return {
    symbol,
    price: 1.25,
    prev_close: 1,
    change_pct: 25,
    change_abs: 0.25,
    gap_percent: 25,
    volume: 1000,
    rel_volume: null,
    has_news: false,
    newest_headline_at: null,
    market_cap: null,
    float: null,
    short_interest: null,
    short_ratio: null,
  };
}

function props(over: Partial<ScannerTableRowProps> = {}): ScannerTableRowProps {
  const aaa = row('AAA');
  return {
    columns: [['symbol', 'Symbol'], ['price', 'Price']],
    row: aaa,
    index: 0,
    selected: false,
    onSelect: vi.fn(),
    onOpenTrading: vi.fn(),
    flash: undefined,
    stale: false,
    ...over,
  };
}

describe('scannerTableRowPropsEqual', () => {
  it('skips reconciliation when the same row object and primitives match', () => {
    const shared = row('AAA');
    const onSelect = vi.fn();
    const onOpenTrading = vi.fn();
    const columns: [string, string][] = [['symbol', 'Symbol']];
    const a = props({ row: shared, onSelect, onOpenTrading, columns });
    const b = props({ row: shared, onSelect, onOpenTrading, columns });
    expect(scannerTableRowPropsEqual(a, b)).toBe(true);
  });

  it('re-renders only when this symbol patched (new row object)', () => {
    const prev = props();
    const next = props({ row: { ...prev.row, price: 2 } });
    expect(scannerTableRowPropsEqual(prev, next)).toBe(false);
  });

  it('re-renders when this row flash or stale flips', () => {
    const shared = row('AAA');
    const onSelect = vi.fn();
    const onOpenTrading = vi.fn();
    const columns: [string, string][] = [['price', 'Price']];
    const base = props({ row: shared, onSelect, onOpenTrading, columns });
    expect(scannerTableRowPropsEqual(base, { ...base, flash: 'up' })).toBe(false);
    expect(scannerTableRowPropsEqual(base, { ...base, stale: true })).toBe(false);
  });
});
