/**
 * The grade you can see (operator report, 2026-09-29): every grade with its count, forming rows
 * included, and a filtered setup kept on its card with its pattern's own state.
 */
import { describe, expect, it } from 'vitest';
import { gradeLabel, gradeWords, pillarCount } from './pillarWords';
import { stateWords, toGoWords } from './setupWords';
import type { SetupRow } from './types';

const AVAT_CHECKS = { price: false, change: true, rvol: false, news: false, float: false };

function row(partial: Partial<SetupRow> = {}): SetupRow {
  return {
    symbol: 'AVAT', setup_type: 'first_pullback', state: 'armed', reason: 'trigger 1.97, stop 1.94, risk 0.04',
    kind: 'second_pullback', nth: 2, setup_id: 'AVAT-2026-09-29-1790683440',
    setup: { trigger: 1.97, entry: 1.98, stop: 1.9403, risk: 0.0397, target1: 2.0594, pullback_bars: 1,
      leg_high: 1.98, leg_low: 1.84, leg_pct: 0.0761, triggered_at: 1_790_683_578 },
    leg: { t: 0, high: 1.98, low: 1.84, pct: 0.0761 }, last_price: 1.96, distance: 0.01, grade: 'C',
    pillars: { price: 1.96, change_pct: 17.4, rvol: 0.44, float: 25_546_730, news: false, headline: null,
      checks: AVAT_CHECKS },
    graded: 'armed', tape: null, proposal: null, outcome: null, bar_r: null, mfe: null, mae: null,
    ...partial,
  };
}

describe('a grade with its count', () => {
  it('counts the pillars that pass and the ones known', () => {
    expect(pillarCount(AVAT_CHECKS)).toEqual({ passed: 1, known: 5, total: 5 });
    expect(pillarCount({ price: true, change: null })).toEqual({ passed: 1, known: 1, total: 2 });
    expect(pillarCount(null)).toBeNull();
    expect(gradeLabel('C', pillarCount(AVAT_CHECKS))).toBe('C 1/5');
    expect(gradeLabel('B', null)).toBe('B');
    expect(gradeLabel(null, null)).toBeNull();
  });

  it('says AVAT is a C on one pillar of five, read when it armed', () => {
    const w = gradeWords(row());
    expect(w.text).toBe('C 1/5');
    const lines = w.tip.split('\n');
    expect(lines[0]).toBe('Grade C: 1 of 5 pillars pass.');
    expect(lines[1]).toMatch(/C = three or fewer: not a trade/);
    expect(lines[2]).toBe('Read when the setup armed.');
    expect(w.tip).toMatch(/✗ Price: 1\.96/);
    expect(w.tip).toMatch(/✓ Up on the day: \+17%/);
    expect(w.tip).toMatch(/✗ Relative volume: 0\.4x/);
  });

  it('grades a forming row from the read taken when its leg made its high', () => {
    const w = gradeWords(row({ state: 'leg', setup: null, graded: 'forming' }));
    expect(w.text).toBe('C 1/5');
    expect(w.tip.split('\n')[2]).toBe('Read when this leg made its high; graded again when the setup arms.');
    expect(gradeWords(row({ grade: null, pillars: null, graded: null })).text).toBe('·');
  });

  it('never shows a fall as a rise', () => {
    const w = gradeWords(row({ pillars: { ...row().pillars!, change_pct: -6.2 } }));
    expect(w.tip).toMatch(/Up on the day: −6%/);
  });
});

describe('a filtered setup on its card', () => {
  it('says where the pattern stands, and how far it is from its trigger', () => {
    const base = { state: 'filtered' as const, reason: 'filtered: float 25.5M over 10.0M' };
    expect(stateWords(row({ ...base, phase: 'armed' })).text).toBe('Filtered · armed');
    expect(stateWords(row({ ...base, phase: 'near' })).text).toBe('Filtered · near');
    expect(stateWords(row({ ...base, phase: 'triggered' })).text).toBe('Filtered · triggered 08:06');
    expect(stateWords(row({ ...base, phase: null })).text).toBe('Filtered');
    expect(stateWords(row({ ...base, phase: 'near' })).tip).toMatch(/never proposes and the bot never takes it/);
    expect(toGoWords(row({ ...base, phase: 'near', distance: 0.01 })).text).toBe('1¢');
    expect(toGoWords(row({ ...base, phase: 'triggered', distance: null })).text).toBe('·');
  });
});
