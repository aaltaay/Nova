import { describe, expect, it } from 'vitest';
import { cutBars, dailyAtCutoff } from './reviewCut';
import { fixturePayload } from './reviewFixture';
import type { RawBar } from '../tickerChartData';

const five: RawBar = {
  t: '2026-09-18T09:55:00-04:00',
  o: 1, h: 2, l: 1, c: 1, v: 10,
};

describe('review cut', () => {
  it('drops a 5-minute bar until that bar has closed', () => {
    expect(cutBars([five], '5m', '2026-09-18T09:58:00-04:00')).toEqual([]);
    expect(cutBars([five], '5m', '2026-09-18T10:00:00-04:00')).toEqual([five]);
  });

  it('drops a daily bar after the session date', () => {
    const bars: RawBar[] = [
      { t: '2026-09-17', o: 1, h: 1, l: 1, c: 1, v: 1 },
      { t: '2026-09-18', o: 2, h: 2, l: 2, c: 2, v: 2 },
      { t: '2026-09-19', o: 3, h: 3, l: 3, c: 3, v: 3 },
    ];
    expect(cutBars(bars, '1d', '2026-09-18T16:00:00-04:00').map((bar) => bar.t)).toEqual([
      '2026-09-17',
      '2026-09-18',
    ]);
  });

  it('keeps a 10-second bar only after that bar has closed', () => {
    const closed: RawBar = { t: '2026-09-18T09:59:50-04:00', o: 4, h: 4, l: 4, c: 4, v: 1 };
    const open: RawBar = { t: '2026-09-18T10:00:00-04:00', o: 80, h: 80, l: 80, c: 80, v: 1 };
    expect(cutBars([closed, open], '10s', '2026-09-18T10:00:00-04:00')).toEqual([closed]);
  });

  it('builds the same-day daily candle from minutes closed by 10:00', () => {
    const minutes: RawBar[] = [
      { t: '2026-09-18T09:59:00-04:00', o: 9, h: 10, l: 8, c: 9.5, v: 1 },
      { t: '2026-09-18T10:15:00-04:00', o: 40, h: 50, l: 40, c: 45, v: 1 },
    ];
    const dailies: RawBar[] = [
      { t: '2026-09-17', o: 1, h: 6, l: 0.5, c: 5.5, v: 10 },
      { t: '2026-09-18', o: 100, h: 200, l: 1, c: 150, v: 999 },
    ];
    const series = dailyAtCutoff('2026-09-18', dailies, minutes, '2026-09-18T10:00:00-04:00');
    expect(series.map((bar) => bar.t)).toEqual(['2026-09-17', '2026-09-18']);
    expect(series[1].h).toBe(10);
    expect(series[1].c).toBe(9.5);
  });

  it('builds fixture levels and the daily candle from bars closed by as_of', () => {
    const payload = fixturePayload('REFR', '2026-09-18', ['1m', '5m', '1d'], '10:00');
    const minutes = payload.timeframes['1m']?.bars ?? [];
    expect(minutes.length).toBeGreaterThan(0);
    expect(minutes.every((bar) => bar.t.slice(11, 16) < '10:00')).toBe(true);
    const hod = Math.max(...minutes.map((bar) => bar.h));
    expect(payload.levels.hod).toBe(hod);
    const daily = payload.timeframes['1d']?.bars.at(-1);
    expect(daily?.t).toBe('2026-09-18');
    expect(daily?.h).toBe(hod);
  });
});
