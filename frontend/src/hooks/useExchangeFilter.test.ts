import { describe, it, expect } from 'vitest';
import { SCANNER_EXCHANGE_DEFAULTS, SCANNER_EXCHANGE_OPTIONS } from '../constants';
import { filterRowsBySelection } from './useExchangeFilter';

type Row = { exchange?: string | null; symbol: string };

const rows: Row[] = [
  { symbol: 'AAPL', exchange: 'NASDAQ' },
  { symbol: 'SOBR', exchange: 'NASDAQ' },
  { symbol: 'CPHI', exchange: 'AMEX' },
  { symbol: 'XYZ', exchange: 'BATS' },
  { symbol: 'NOXCH', exchange: null },
  { symbol: 'NOEXCH', exchange: undefined },
];

describe('exchange filterRows', () => {
  it('defaults to all exchanges -- a narrow default silently hid real movers', () => {
    expect(SCANNER_EXCHANGE_DEFAULTS).toEqual([...SCANNER_EXCHANGE_OPTIONS]);
  });

  it('NASDAQ-only keeps NASDAQ rows and fails open on unknown-exchange rows', () => {
    // 2026-08-25: IBKR roster rows arrive with exchange=null before a listing
    // exchange is known. A filter that drops them blanked the desk to 1 row.
    const out = filterRowsBySelection(['NASDAQ'], rows);
    expect(out.map(r => r.symbol)).toEqual(['AAPL', 'SOBR', 'NOXCH', 'NOEXCH']);
  });

  it('NASDAQ-only still drops a row with a KNOWN, unselected exchange', () => {
    const out = filterRowsBySelection(['NASDAQ'], rows);
    expect(out.map(r => r.symbol)).not.toContain('CPHI');
    expect(out.map(r => r.symbol)).not.toContain('XYZ');
  });

  it('NASDAQ + AMEX keeps both known exchanges plus unknown rows', () => {
    const out = filterRowsBySelection(['NASDAQ', 'AMEX'], rows);
    expect(out.map(r => r.symbol)).toContain('CPHI');
    expect(out.map(r => r.symbol)).toContain('AAPL');
    expect(out.map(r => r.symbol)).not.toContain('XYZ');
  });

  it('all-options selected returns full list (passthrough)', () => {
    const out = filterRowsBySelection([...SCANNER_EXCHANGE_OPTIONS], rows);
    expect(out).toHaveLength(rows.length);
  });

  it('rows with null/undefined exchange are always kept (fail open)', () => {
    const out = filterRowsBySelection(['NASDAQ'], rows);
    expect(out.find(r => r.symbol === 'NOXCH')).toBeDefined();
    expect(out.find(r => r.symbol === 'NOEXCH')).toBeDefined();
  });

  it('keeps rows whose venue is not one of the options (QA C52: they vanished before)', () => {
    const odd: Row[] = [
      { symbol: 'OTCX', exchange: 'OTC' },
      { symbol: 'PINK', exchange: 'PINK' },
      { symbol: 'LOWER', exchange: 'nasdaq' },
      { symbol: 'CPHI', exchange: 'AMEX' },
    ];
    const out = filterRowsBySelection(['NASDAQ'], odd).map(r => r.symbol);
    expect(out).toEqual(['OTCX', 'PINK', 'LOWER']);
  });
});
