/**
 * Too thin to trade (operator decision 2026-10-01, on LPA): the reading off the wire, its words and the greyed row.
 */
import { describe, expect, it } from 'vitest';
import { isThin, liquidityTip, money, normalizeLiquidity, thinChip } from './liquidity';
import { rowClass } from './setupsFormat';
import type { SetupRow } from './types';

/** LPA's first pullback at 09:41 as the backend judged it (`setup_scanner/liquidity.py`). */
const LPA_THIN_WIRE = {
  state: 'thin',
  reasons: [
    'traded $999K today, under $2.00M',
    '$43K in the last 5 minutes, under $100K',
    'buying 333 shares walks the asks to 3.33: 14c over the 3.12 ask on average, 2.3R of the 6c risk',
  ],
  failed: ['day', 'pace', 'book'],
  unknown: {},
  day_dollars: 999_309,
  pace_dollars: 42_539,
  pace_sec: 300,
  walk: { qty: 333, best_ask: 3.12, last: 3.33, avg: 3.2609, over_ask: 0.1409, shown: 830, short: false, r: 2.35 },
  as_of: 1_790_862_062,
  limits: { day_dollars: 2_000_000, pace_dollars: 100_000, walk_r: 0.25 },
};

describe('normalizeLiquidity', () => {
  it('reads LPA whole', () => {
    const r = normalizeLiquidity(LPA_THIN_WIRE)!;
    expect(r.state).toBe('thin');
    expect(r.failed).toEqual(['day', 'pace', 'book']);
    expect(r.walk).toMatchObject({ qty: 333, best_ask: 3.12, r: 2.35, short: false });
    expect(r.limits).toEqual({ day_dollars: 2_000_000, pace_dollars: 100_000, walk_r: 0.25 });
    expect(isThin(r)).toBe(true);
  });

  it('is null for an older backend or something that is not a reading', () => {
    expect(normalizeLiquidity(undefined)).toBeNull();
    expect(normalizeLiquidity({ state: 'maybe' })).toBeNull();
    expect(isThin(null)).toBe(false);
  });
});

describe('the words', () => {
  it('says each failed check, then the rule, on hover', () => {
    const chip = thinChip(normalizeLiquidity(LPA_THIN_WIRE))!;
    expect(chip.text).toBe('Too thin');
    expect(chip.tip.split('\n').slice(0, 2)).toEqual([
      'Traded $999K today, under $2.00M.',
      '$43K in the last 5 minutes, under $100K.',
    ]);
    expect(chip.tip).toContain('Nova never buys it, never proposes it');
  });

  it('gives no chip to a liquid or unknown reading, and says what was not known', () => {
    const unknown = normalizeLiquidity({ ...LPA_THIN_WIRE, state: 'unknown', reasons: [], failed: [],
      unknown: { day: "Nova does not know today's volume" } })!;
    expect(thinChip(unknown)).toBeNull();
    expect(liquidityTip(unknown)).toContain("Not known: Nova does not know today's volume.");
  });

  it('formats dollars the way the backend does', () => {
    expect([money(999_309), money(2_000_000), money(42_539), money(800), money(null)])
      .toEqual(['$999K', '$2.00M', '$43K', '$800', '?']);
  });

  it('greys a thin row on the board', () => {
    const row = { symbol: 'LPA', state: 'near', proposal: null, liquidity: LPA_THIN_WIRE } as unknown as SetupRow;
    expect(rowClass(row)).toBe('setups-row setups-row--near setups-row--thin');
    expect(rowClass({ ...row, liquidity: null })).toBe('setups-row setups-row--near');
  });
});
