import { describe, expect, it } from 'vitest';
import { chartKey } from './paneKeyRows';

const ON = { setups: true, levels: true };
const LULD = 'Halt line (LULD, 9:30 AM–4:00 PM)';
const titles = (kind: Parameters<typeof chartKey>[0], layers = ON) => chartKey(kind, layers).map(s => s.title);

describe("each chart pane's Key", () => {
  it('names the levels the 5-minute candles show and the time-of-day background', () => {
    expect(titles('map')).toEqual([
      '5-minute setups (labels start "5m")', '5-minute flat top (a strategy: it can trade)',
      'Levels from 5-minute candles (hover a label for why)', 'Trend lines from 5-minute candles (hover one for why)',
      'Background (time of day, ET)',
    ]);
    expect(chartKey('map', ON)[0].rows.map(r => r.label)).toEqual(
      ['Forming', 'Armed / near', 'Ended (faint)', '5m trigger', 'Scored only']);
    const rows = chartKey('map', ON)[2].rows.map(r => r.label);
    // The 5-minute map keeps a round only where its candles made a level, which takes that level's colour.
    expect(rows).toEqual(['Resistance', 'Support', 'Shaded band', 'Thick line']);
    // Yesterday's and old daily levels belong to the Full Day pane only.
    expect(rows).not.toContain("Yesterday's");
    expect(rows).not.toContain('Old daily level');
    expect(chartKey('map', ON)[4].rows.map(r => r.label)).toEqual(['Premarket', 'Regular hours', 'After hours', 'Closed']);
  });

  it("names past days' levels on the Full Day pane, which has no session background", () => {
    const key = chartKey('daily', ON);
    expect(key).toHaveLength(1);
    expect(key[0].rows.map(r => r.label)).toEqual(expect.arrayContaining(['Old daily level', "Yesterday's"]));
  });

  it("names the setups, the plan and the 1-minute candles' levels on the 1-minute", () => {
    expect(titles('full')).toEqual([
      'Setups', 'Flat top', 'Pullback dip (watch only: never traded)', 'The plan',
      'Levels from 1-minute candles (hover a label for why)',
      'Trend lines from 1-minute candles (hover one for why)', 'From the 5-minute chart', LULD,
      'Background (time of day, ET)',
    ]);
    expect(titles('full', { setups: false, levels: false })).toEqual(['The plan', LULD, 'Background (time of day, ET)']);
    const levels = chartKey('full', ON)[4].rows.map(r => r.label);
    // #847: the watch-only pullback dip's marks, in its own pink.
    expect(chartKey('full', ON)[2].rows.map(r => r.label)).toEqual(['Dip', 'Bottom', 'Entry candle']);
    expect(levels).toEqual(['Resistance', 'Support', 'Round number', 'Shaded band', 'Thick line']);
  });

  it('names the trend lines each minute pane reads from its own candles, with their rising and falling swatches', () => {
    for (const pane of ['full', 'map'] as const) {
      const trend = chartKey(pane, ON).find(s => s.title.startsWith('Trend lines'));
      expect(trend?.rows.map(r => [r.swatch, r.label])).toEqual([
        ['rise', 'Ascending support'], ['fall', 'Descending resistance'], ['ring', 'Touch'], ['dash', 'Dashed'],
        ['dots', 'Faint, ✕'],
      ]);
    }
    expect(chartKey('daily', ON).some(s => s.title.startsWith('Trend lines'))).toBe(false);
    expect(chartKey('full', { ...ON, levels: false }).some(s => s.title.startsWith('Trend lines'))).toBe(false);
  });

  it('lists only the plan lines on the 10-second, saying when they show', () => {
    expect(chartKey('thin', ON)[0]).toMatchObject({ title: 'The plan (from near or armed, or while an order works)' });
    expect(chartKey('thin', ON)[0].rows.map(r => r.label)).toEqual(['Entry', 'Stop', 'Target 1 / 2', 'Dashed vs solid']);
  });

  it("lists no plan on the 5-minute, which draws its own setups' lines and never the plan's (operator report 2026-10-13)", () => {
    expect(titles('map').some(t => t.startsWith('The plan'))).toBe(false);
  });

  it('lists nothing for levels that are switched off, and nothing on a pane Nova does not draw on', () => {
    expect(titles('map', { setups: false, levels: false })).toEqual(['Background (time of day, ET)']);
    expect(titles('map', { ...ON, levels: false })).toEqual(
      ['5-minute setups (labels start "5m")', '5-minute flat top (a strategy: it can trade)',
        'Background (time of day, ET)']);
  });

  it("draws the flat top's own marks: its line, a ring per touch, the base, the break and the hold", () => {
    const flat = chartKey('full', ON).find(s => s.title === 'Flat top');
    expect(flat?.rows.map(r => [r.swatch, r.label])).toEqual([
      ['line', 'Flat top'], ['ring', 'Touch'], ['box', 'Base'], ['up', 'Break'], ['box', 'Hold'],
    ]);
    // The 5-minute flat top (a strategy since 2026-10-06): its hold is a 1-minute candle in its 5-minute one.
    const five = chartKey('map', ON).find(s => s.title.startsWith('5-minute flat top'));
    expect(five?.rows.map(r => r.label)).toEqual(['Flat top', 'Touch', 'Base', 'Break', '1m hold']);
    expect(chartKey('full', ON).find(s => s.title === 'From the 5-minute chart')?.rows.map(r => r.label))
      .toEqual(['5m trigger', '5m flat top']);
    expect(chartKey('none', ON)).toEqual([]);
  });

  it("lists Nova's LULD band on the 1-minute Key alone, and not with Eyes off (ADR 047 amendment 2026-10-12)", () => {
    const luld = chartKey('full', ON).find(k => k.title === LULD);
    expect(luld?.rows.map(r => [r.swatch, r.label])).toEqual([['line', 'LULD ▲ / ▼'], ['dash', 'Dashed, ≈']]);
    expect(titles('full', { ...ON, eyes: false })).not.toContain(LULD);
    for (const pane of ['map', 'thin', 'daily'] as const) expect(titles(pane)).not.toContain(LULD);
  });
});
