import { describe, expect, it } from 'vitest';
import { applyScannerHaltPatch, normalizeHaltRows } from './scannerHaltPatch';
import { applyBoardChips } from './boardFilters';

it('a newly halted frozen row passes the chip without changing its market fields', () => {
  const rows = [{ symbol: 'PFSA', halted: false, price: 4.3, volume: 10, quote_ts: 100 }];
  const next = applyScannerHaltPatch(rows, [{ symbol: 'pfsa', halted: true }]);
  expect(next[0]).toEqual({ ...rows[0], halted: true });
  expect(rows[0].halted).toBe(false);
  expect(applyBoardChips(next, new Set(['halted']))).toHaveLength(1);
  expect(applyBoardChips(applyScannerHaltPatch(next, [{ symbol: 'PFSA', halted: false }]), new Set(['halted']))).toEqual([]);
  expect(applyBoardChips(applyScannerHaltPatch(next, [{ symbol: 'PFSA', halted: null }]), new Set(['halted']))).toHaveLength(1);
});

describe('halt shape gate', () => {
  it('rejects missing symbols and untyped evidence', () => {
    expect(normalizeHaltRows([{ symbol: ' pfsa ', halted: true }, { symbol: 'X', halted: 'false' }, {}, null]))
      .toEqual([{ symbol: 'PFSA', halted: true }]);
    expect(normalizeHaltRows(null)).toEqual([]);
  });
  it('keeps array identity when nothing changed and never admits a new symbol', () => {
    const rows = [{ symbol: 'PFSA', halted: true, price: 4.3 }];
    expect(applyScannerHaltPatch(rows, [{ symbol: 'OTHER', halted: true }])).toBe(rows);
    expect(applyScannerHaltPatch(rows, [{ symbol: 'PFSA', halted: true }])).toBe(rows);
  });
});
