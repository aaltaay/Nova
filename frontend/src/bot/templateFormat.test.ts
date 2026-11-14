import { describe, expect, it } from 'vitest';
import { templatesPayload } from './botsPageFixtures';
import { changedKeys, formatValue, parseInput } from './templateFormat';
import type { ParamSpec } from './templateTypes';

const payload = templatesPayload();
const fp = payload.setups.find(s => s.id === 'first_pullback')!;
const spec = (key: string): ParamSpec => fp.catalogue.groups.flatMap(g => g.params).find(p => p.key === key)!;
const defaults = fp.templates[0].values;

describe('templateFormat', () => {
  it('formats each value in its own unit', () => {
    expect(formatValue(spec('stop_cap'), 0.2)).toBe('$0.20');
    expect(formatValue(spec('leg_pct'), 5)).toBe('5%');
    expect(formatValue(spec('leg_window'), 10)).toBe('10 bars');
    expect(formatValue(spec('session_start'), '07:00')).toBe('07:00 ET');
    expect(formatValue(spec('max_float_m'), null)).toBe('off');
    expect(formatValue(spec('max_float_m'), 10)).toBe('10M');
    expect(formatValue(spec('wall'), 25000)).toBe('25,000 shares');
    expect(formatValue(spec('require_hod'), true)).toBe('on');
    // The target menu (#845): each choice in the catalogue's own words, the fixed amount past the entry, the split.
    expect(formatValue(spec('target1_kind'), 'round_or_fixed'))
      .toBe('the fixed amount, or 1c under a half / whole dollar when that is closer');
    expect(formatValue(spec('target2_kind'), 'none')).toBe('none: everything sells at target 1');
    expect(formatValue(spec('target_fixed'), 0.2)).toBe('$0.20 past the entry');
    expect(formatValue(spec('target_split_pct'), 50)).toBe('50% of the shares');
    expect(formatValue(spec('stop_kind'), 'pattern')).toBe("the pattern's own");
    // No 2R target is left in the catalogue: R is the unit results are measured in, never a target.
    const keys = fp.catalogue.groups.flatMap(g => g.params.map(p => p.key));
    expect(keys).not.toContain('target_r');
    expect(keys).not.toContain('target_mode');
  });

  it('parses typed text against the parameter, and an empty filter turns it off', () => {
    expect(parseInput(spec('leg_window'), '12')).toEqual({ value: 12 });
    expect(parseInput(spec('leg_window'), '2.5')).toEqual({ error: 'a whole number' });
    expect(parseInput(spec('leg_pct'), '0')).toEqual({ error: 'at least 1' });
    expect(parseInput(spec('session_start'), '7:00')).toEqual({ error: 'a time like 07:00' });
    expect(parseInput(spec('max_float_m'), '')).toEqual({ value: null });
    expect(parseInput(spec('stop_cap'), 'abc')).toEqual({ error: 'a number' });
  });


  it('says what a variation changed', () => {
    expect(changedKeys(defaults, { ...defaults, leg_pct: 6 })).toEqual(['leg_pct']);
    expect(changedKeys(defaults, { ...defaults })).toEqual([]);
  });
});
