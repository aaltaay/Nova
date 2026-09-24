import { describe, expect, it } from 'vitest';
import { templatesPayload } from './botsPageFixtures';
import { changedKeys, formatValue, parseInput, readoutText, ruleLines, ruleSummary, tapeLines } from './templateFormat';
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

  it('writes the bull flag, the flat top and red to green in the numbers their scanners run (ADR 031)', () => {
    const values = (id: string) => payload.setups.find(s => s.id === id)!.templates[0].values;
    expect(Object.fromEntries(ruleLines('bull_flag', values('bull_flag')))).toEqual({
      Stock: 'HOD Momo names · any price · any float',
      Setup: 'Pole of 3+ green candles up ≥ 5% (or $0.30) on rising volume · 2–3 red candles give back ≤ 50% of it'
        + ' on lighter volume, closes hold the 9 EMA · MACD above zero · the day\'s biggest candle not red'
        + ' · pole-top wick ≤ 40%',
      Entry: "Over the last flag candle's high +$0.01 · arms 07:00–11:30 · only when the tape says GO",
      Trade: 'Risk $0.03–0.20 · target 1 the pole high or 2R · bot 07:00–10:00, 1 a day',
    });
    expect(Object.fromEntries(ruleLines('flat_top_breakout', values('flat_top_breakout')))).toMatchObject({
      Setup: 'Impulse ≥ 3% into the high of day · 2–6 candles close within 2% under it, lows over the 9 EMA'
        + ' · MACD above zero',
      Entry: 'A green candle holding over the high within 3 candles, at its close +$0.01 · arms 07:00–11:30'
        + ' · only when the tape says GO',
      Trade: 'Risk $0.03–0.20 · target 1 2R · bot 07:00–10:00, 1 a day',
    });
    expect(Object.fromEntries(ruleLines('flat_top_breakout', { ...values('flat_top_breakout'), ft_entry: 'break' })).Entry)
      .toBe('The break of the high +$0.01 · arms 07:00–11:30 · only when the tape says GO');
    expect(Object.fromEntries(ruleLines('red_to_green', values('red_to_green')))).toMatchObject({
      Setup: '1+ close under the 09:30 open, then back through it by 10:30 · one try a day · MACD above zero',
      Entry: 'Over the open +$0.01 · only when the tape says GO',
      Trade: 'Risk $0.03–0.20 · target 1 2R or the high of day, whichever is higher · bot 07:00–10:00, 1 a day',
    });
    expect(ruleSummary('first_pullback', defaults)).toBe('Leg ≥ 5% · 1–3 bar pullback · stop at the pullback low');
    expect(ruleSummary('bull_flag', values('bull_flag'))).toBe('Pole 3+ green, ≥ 5% · 2–3 bar flag · stop at the flag low');
    expect(ruleSummary('flat_top_breakout', values('flat_top_breakout')))
      .toBe('2–6 bar base within 2% of the high · buy a green hold over it');
    expect(ruleSummary('red_to_green', values('red_to_green'))).toBe('1+ red under the 09:30 open · reclaim by 10:30');
    expect(ruleSummary('gap_and_go', {})).toBe('');
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
