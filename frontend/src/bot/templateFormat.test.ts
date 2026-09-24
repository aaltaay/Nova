import { describe, expect, it } from 'vitest';
import { templatesPayload } from './botsPageFixtures';
import { changedKeys, formatValue, parseInput, readoutText, ruleLines, tapeLines } from './templateFormat';
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
    expect(formatValue(spec('target_mode'), 'fixed')).toBe('a fixed amount over the entry');
  });

  it('parses typed text against the parameter, and an empty filter turns it off', () => {
    expect(parseInput(spec('leg_window'), '12')).toEqual({ value: 12 });
    expect(parseInput(spec('leg_window'), '2.5')).toEqual({ error: 'a whole number' });
    expect(parseInput(spec('leg_pct'), '0')).toEqual({ error: 'at least 1' });
    expect(parseInput(spec('session_start'), '7:00')).toEqual({ error: 'a time like 07:00' });
    expect(parseInput(spec('max_float_m'), '')).toEqual({ value: null });
    expect(parseInput(spec('stop_cap'), 'abc')).toEqual({ error: 'a number' });
  });

  it('writes the default first pullback in the numbers the scanner runs', () => {
    expect(Object.fromEntries(ruleLines('first_pullback', defaults))).toEqual({
      Stock: 'HOD Momo names · any price · any float',
      Setup: 'Leg ≥ 5% to a new high of day · 1–3 candles hold the 9 EMA and give back < 50% of the leg · MACD above zero',
      Entry: "Over the last pullback candle's high +$0.01 · arms 07:00–11:30 · only when the tape says GO",
      Trade: 'Risk $0.03–0.20 · target 1 the leg high or 2R · bot 07:00–10:00, 1 a day',
    });
  });

  it('says what a variation changed', () => {
    const lines = Object.fromEntries(ruleLines('first_pullback', {
      ...defaults, min_price: 3, max_price: 10, max_float_m: 10, min_grade: 'B', require_catalyst: true,
      target_mode: 'fixed', target_fixed: 0.2,
    }));
    expect(lines.Stock).toBe('HOD Momo names · $3–10 · float ≤ 10M · a catalyst · grade B+');
    expect(lines.Trade).toContain('target 1 entry + $0.20');
    expect(changedKeys(defaults, { ...defaults, leg_pct: 6 })).toEqual(['leg_pct']);
  });

  it('draws the tape gate and the research setups from their own values', () => {
    expect(tapeLines(defaults).map(([v, t]) => `${v}: ${t}`)).toEqual([
      'go: green prints (3+ at the ask), nothing holding the level',
      'wait: 25k+ seller not thinning',
      'veto: spread over $0.05 / 100k+ seller',
      'blind: no Level 2',
    ]);
    const gng = payload.setups.find(s => s.id === 'gap_and_go')!.templates[0].values;
    expect(Object.fromEntries(ruleLines('gap_and_go', gng)).Trade).toBe('Stop $0.20 or 4% · half at 2R, the rest at 4R · out 11:30');
    expect(ruleLines('micro_pullback', {})).toEqual([]);
    expect(readoutText(fp.templates[0])).toBe('collecting 12 / 50');
  });
});
