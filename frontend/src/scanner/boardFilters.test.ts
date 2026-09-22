import { describe, expect, it } from 'vitest';
import {
  SCANNER_CHIP_IDS,
  SCANNER_CHIP_LABEL,
  SCANNER_CHIP_TITLE,
} from '../constantGroups/scanner_board';
import {
  applyBoardChips,
  chipPasses,
  chipsInOrder,
  isChipAvailable,
  sameChips,
  type ChipRow,
} from './boardFilters';

function row(over: Partial<ChipRow> & { symbol: string }): ChipRow & { symbol: string } {
  return { gap_percent: 0.2, float: 8_000_000, rel_volume: 4, has_news: true, ...over };
}

describe('boardFilters', () => {
  it('Gap >= 10% compares the fraction the live row carries', () => {
    expect(chipPasses('gap', row({ symbol: 'A', gap_percent: 0.10 }))).toBe(true);
    expect(chipPasses('gap', row({ symbol: 'B', gap_percent: 0.099 }))).toBe(false);
    expect(chipPasses('gap', row({ symbol: 'C', gap_percent: -0.3 }))).toBe(false);
  });

  it('Float <= 20M and Rel vol >= 3 use the row values', () => {
    expect(chipPasses('float', row({ symbol: 'A', float: 20_000_000 }))).toBe(true);
    expect(chipPasses('float', row({ symbol: 'B', float: 20_000_001 }))).toBe(false);
    expect(chipPasses('relvol', row({ symbol: 'C', rel_volume: 3 }))).toBe(true);
    expect(chipPasses('relvol', row({ symbol: 'D', rel_volume: 2.9 }))).toBe(false);
  });

  it('fails open on an unknown fact -- a null never hides a row', () => {
    expect(chipPasses('gap', row({ symbol: 'A', gap_percent: null }))).toBe(true);
    expect(chipPasses('float', row({ symbol: 'B', float: null }))).toBe(true);
    expect(chipPasses('relvol', row({ symbol: 'C', rel_volume: null }))).toBe(true);
  });

  it('Has news is the boolean the row carries', () => {
    expect(chipPasses('news', row({ symbol: 'A', has_news: true }))).toBe(true);
    expect(chipPasses('news', row({ symbol: 'B', has_news: false }))).toBe(false);
  });

  it('Halted cannot filter yet and says so', () => {
    expect(isChipAvailable('halted')).toBe(false);
    expect(chipPasses('halted', row({ symbol: 'A' }))).toBe(true);
    expect(SCANNER_CHIP_TITLE.halted).toMatch(/not carried on scanner rows/);
    expect(applyBoardChips([row({ symbol: 'A' })], new Set(['halted']))).toHaveLength(1);
  });

  it('applies every active chip and reports what is left', () => {
    const rows = [
      row({ symbol: 'KEEP' }),
      row({ symbol: 'LOWGAP', gap_percent: 0.02 }),
      row({ symbol: 'BIGFLOAT', float: 90_000_000 }),
      row({ symbol: 'QUIET', has_news: false }),
    ];
    expect(applyBoardChips(rows, new Set()).map((r) => r.symbol)).toEqual(['KEEP', 'LOWGAP', 'BIGFLOAT', 'QUIET']);
    expect(applyBoardChips(rows, new Set(['gap'])).map((r) => r.symbol)).toEqual(['KEEP', 'BIGFLOAT', 'QUIET']);
    expect(applyBoardChips(rows, new Set(['gap', 'float', 'news'])).map((r) => r.symbol)).toEqual(['KEEP']);
  });

  it('has a label for every chip and orders chips canonically', () => {
    for (const id of SCANNER_CHIP_IDS) expect(SCANNER_CHIP_LABEL[id]).toBeTruthy();
    expect(chipsInOrder(new Set(['news', 'gap']))).toEqual(['gap', 'news']);
    expect(sameChips(new Set(['gap', 'news']), ['news', 'gap'])).toBe(true);
    expect(sameChips(new Set(['gap']), ['news', 'gap'])).toBe(false);
  });
});
