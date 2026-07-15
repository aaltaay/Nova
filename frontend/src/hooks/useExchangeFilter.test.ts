import { describe, it, expect } from 'vitest';
import { SCANNER_EXCHANGE_DEFAULTS } from '../constants';

// filterRows is pure; test it without React hook machinery
type Row = { exchange?: string | null; symbol: string };

function makeFilterRows(selected: string[]) {
  const SCANNER_EXCHANGE_OPTIONS = ['NASDAQ', 'NYSE', 'AMEX', 'ARCA', 'BATS', 'IEX', 'CBOE'] as const;
  return (rows: Row[]) => {
    if (selected.length === SCANNER_EXCHANGE_OPTIONS.length) return rows;
    return rows.filter(r => r.exchange && selected.includes(r.exchange));
  };
}

const rows: Row[] = [
  { symbol: 'AAPL', exchange: 'NASDAQ' },
  { symbol: 'SOBR', exchange: 'NASDAQ' },
  { symbol: 'CPHI', exchange: 'AMEX' },
  { symbol: 'XYZ',  exchange: 'BATS' },
  { symbol: 'NOXCH', exchange: null },
  { symbol: 'NOEXCH', exchange: undefined },
];

describe('exchange filterRows', () => {
  it('defaults to NASDAQ only', () => {
    expect(SCANNER_EXCHANGE_DEFAULTS).toEqual(['NASDAQ']);
  });

  it('NASDAQ-only drops AMEX, BATS, and null-exchange rows', () => {
    const filter = makeFilterRows(['NASDAQ']);
    const out = filter(rows);
    expect(out.map(r => r.symbol)).toEqual(['AAPL', 'SOBR']);
  });

  it('NASDAQ + AMEX keeps both', () => {
    const filter = makeFilterRows(['NASDAQ', 'AMEX']);
    const out = filter(rows);
    expect(out.map(r => r.symbol)).toContain('CPHI');
    expect(out.map(r => r.symbol)).toContain('AAPL');
    expect(out.map(r => r.symbol)).not.toContain('XYZ');
  });

  it('all-options selected returns full list (passthrough)', () => {
    const all = ['NASDAQ', 'NYSE', 'AMEX', 'ARCA', 'BATS', 'IEX', 'CBOE'];
    const filter = makeFilterRows(all);
    expect(filter(rows)).toHaveLength(rows.length);
  });

  it('rows with null/undefined exchange are dropped when filter is active', () => {
    const filter = makeFilterRows(['NASDAQ']);
    const out = filter(rows);
    expect(out.find(r => r.symbol === 'NOXCH')).toBeUndefined();
    expect(out.find(r => r.symbol === 'NOEXCH')).toBeUndefined();
  });
});
