import { describe, expect, it } from 'vitest';
import { floatShade, rowShades, volumeShade } from './rowShades';

const row = (over: Record<string, unknown> = {}) => ({
  float: 630_935, volume: 111_968_235, rel_volume: 429.17, rvol_source: 'daily_avg',
  float_contradicted: false, shares_issued: null, ...over,
});

describe('row shades (one rule for every Scanner list)', () => {
  it('shades a float under 10M bright, 10-20M second, and nothing above', () => {
    expect(floatShade(row({ float: 4_469_975 }))).toBe('low');
    expect(floatShade(row({ float: 10_000_000 }))).toBe('mid');
    expect(floatShade(row({ float: 19_139_433 }))).toBe('mid');
    expect(floatShade(row({ float: 20_000_000 }))).toBe('mid');
    expect(floatShade(row({ float: 22_550_189 }))).toBeNull();
  });

  it('never shades an unknown or doubtful float', () => {
    expect(floatShade(row({ float: null }))).toBeNull();
    expect(floatShade(row({ float: 730_450, float_contradicted: true }))).toBeNull();
    expect(floatShade(row({ float: 631_000, shares_issued: { form: '8-K' } }))).toBeNull();
  });

  it('deepens the volume shade up to 1M shares, then stays', () => {
    expect([44_000, 227_000, 772_400, 1_000_000, 37_911_231].map(volumeShade)).toEqual([1, 2, 4, 5, 5]);
    expect(volumeShade(1)).toBe(1);
    expect(volumeShade(0)).toBeNull();
    expect(volumeShade(null)).toBeNull();
  });

  it('lights the whole row for a low float and a day relative volume of 5x or more', () => {
    expect(rowShades(row()).hot).toBe(true);                                       // AMOD 2026-10-02
    expect(rowShades(row({ rel_volume: 4.9 })).hot).toBe(false);
    expect(rowShades(row({ float: 22_550_189, rel_volume: 5.97 })).hot).toBe(false);
    expect(rowShades(row({ rel_volume: null })).hot).toBe(false);
    // a Sim playback row's time-of-day RVOL is another basis: never read as a day multiple (the Rel vol chip's rule)
    expect(rowShades(row({ rvol_source: 'time_of_day_20' })).hot).toBe(false);
  });

  it('leaves the Large Cap swing table plain', () => {
    expect(rowShades(row(), 'large_cap')).toEqual({ float: null, volume: null, hot: false });
    expect(rowShades(row(), 'gainers')).toEqual({ float: 'low', volume: 5, hot: true });
  });
});
