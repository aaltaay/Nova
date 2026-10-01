import { describe, expect, it } from 'vitest';
import { chartKey } from './paneKeyRows';

const ON = { setups: true, levels: true };
const titles = (kind: Parameters<typeof chartKey>[0], layers = ON) => chartKey(kind, layers).map(s => s.title);

describe("each chart pane's Key", () => {
  it('names the levels the 5-minute candles show and the time-of-day background', () => {
    expect(titles('map')).toEqual([
      '5-minute setups (labels start "5m")', 'Levels from 5-minute candles (hover a label for why)',
      'Background (time of day, ET)',
    ]);
    expect(chartKey('map', ON)[0].rows.map(r => r.label)).toEqual(
      ['Forming', 'Armed / near', 'Ended (faint)', '5m trigger', 'Scored only']);
    const rows = chartKey('map', ON)[1].rows.map(r => r.label);
    expect(rows).toContain('Round dollar');
    // Yesterday's and old daily levels belong to the Full Day pane only.
    expect(rows).not.toContain("Yesterday's");
    expect(rows).not.toContain('Old daily level');
    expect(chartKey('map', ON)[2].rows.map(r => r.label)).toEqual(['Premarket', 'Regular hours', 'After hours', 'Closed']);
  });

  it("names past days' levels on the Full Day pane, which has no session background", () => {
    const key = chartKey('daily', ON);
    expect(key).toHaveLength(1);
    expect(key[0].rows.map(r => r.label)).toEqual(expect.arrayContaining(['Old daily level', "Yesterday's"]));
  });

  it("names the setups, the plan and the 1-minute candles' levels on the 1-minute", () => {
    expect(titles('full')).toEqual([
      'Setups', 'The plan', 'Levels from 1-minute candles (hover a label for why)', 'From the 5-minute chart',
      'Background (time of day, ET)',
    ]);
    expect(titles('full', { setups: false, levels: false })).toEqual(['The plan', 'Background (time of day, ET)']);
    const levels = chartKey('full', ON)[2].rows.map(r => r.label);
    expect(levels).toEqual(['Resistance', 'Support', 'Round dollar', 'Shaded band', 'Thick line']);
  });

  it('lists only the plan lines on the 10-second', () => {
    expect(chartKey('thin', ON)[0].rows.map(r => r.label)).toEqual(['Entry', 'Stop', 'Target', 'Dashed vs solid']);
  });

  it('lists nothing for levels that are switched off, and nothing on a pane Nova does not draw on', () => {
    expect(titles('map', { setups: false, levels: false })).toEqual(['Background (time of day, ET)']);
    expect(titles('map', { ...ON, levels: false })).toEqual(['5-minute setups (labels start "5m")', 'Background (time of day, ET)']);
    expect(chartKey('none', ON)).toEqual([]);
  });
});
