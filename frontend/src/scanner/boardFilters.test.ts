import { describe, expect, it } from 'vitest';
import {
  SCANNER_CHIP_IDS,
  SCANNER_CHIP_LABEL,
  SCANNER_CHIP_LIVE_WHY,
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

  it('Halted is available on a played-back board only, and says why on the live one (#487)', () => {
    expect(isChipAvailable('halted')).toBe(false);
    expect(isChipAvailable('halted', false)).toBe(false);
    expect(isChipAvailable('halted', true)).toBe(true);
    for (const id of SCANNER_CHIP_IDS.filter((c) => c !== 'halted')) {
      expect(isChipAvailable(id)).toBe(true);
      expect(isChipAvailable(id, true)).toBe(true);
    }
    expect(SCANNER_CHIP_LIVE_WHY.halted).toMatch(/Live scanner rows carry no halt state/);
    expect(SCANNER_CHIP_LIVE_WHY.halted).toMatch(/filters played-back days/);
    expect(SCANNER_CHIP_TITLE.halted).toMatch(/not known is kept/);
  });

  it('Halted keeps a row stated halted or not known (fail open) and drops one stated not halted', () => {
    expect(chipPasses('halted', row({ symbol: 'A', halted: true }))).toBe(true);
    expect(chipPasses('halted', row({ symbol: 'B', halted: null }))).toBe(true);
    expect(chipPasses('halted', row({ symbol: 'C', halted: false }))).toBe(false);
    expect(chipPasses('halted', row({ symbol: 'D' }))).toBe(true);
    const rows = [
      row({ symbol: 'HALT', halted: true }),
      row({ symbol: 'UNKNOWN', halted: null }),
      row({ symbol: 'TRADING', halted: false }),
    ];
    const halted = new Set(['halted'] as const);
    expect(applyBoardChips(rows, halted, true).map((r) => r.symbol)).toEqual(['HALT', 'UNKNOWN']);
    // The live board cannot answer it: the chip never filters there.
    expect(applyBoardChips(rows, halted).map((r) => r.symbol)).toEqual(['HALT', 'UNKNOWN', 'TRADING']);
    expect(applyBoardChips(rows, halted, false)).toHaveLength(3);
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

describe('Has news reads the catalyst verdict (ADR 024)', () => {
  const verdict = {
  verdict: 'catalyst', category: 'merger_acquisition', strength: 'weak', title: 'Acme to Acquire Widget Co',
  source: 'prnewswire', published_ts: 1_790_000_000, url: null, negative_too: false, rules_version: 'v5',
} as const;
  it('keeps company news and drops a movers list or a market wrap', () => {
    expect(chipPasses('news', row({ symbol: 'A', catalyst: verdict }))).toBe(true);
    expect(chipPasses('news', row({ symbol: 'B', catalyst: { ...verdict, verdict: 'negative', category: 'delisting_split' } }))).toBe(true);
    expect(chipPasses('news', row({ symbol: 'C', has_news: true, catalyst: { ...verdict, verdict: 'noise_only' } }))).toBe(false);
    expect(chipPasses('news', row({ symbol: 'D', catalyst: { ...verdict, verdict: 'routine_only' } }))).toBe(false);
    expect(chipPasses('news', row({ symbol: 'E', catalyst: { ...verdict, verdict: 'none_found', news_pending: true } }))).toBe(true);
  });
  it('keeps a row whose news is not read yet, and a row without the field keeps the old rule', () => {
    expect(chipPasses('news', row({ symbol: 'F', has_news: false, catalyst: null }))).toBe(true);
    expect(chipPasses('news', row({ symbol: 'G', has_news: false }))).toBe(false);
  });
});
