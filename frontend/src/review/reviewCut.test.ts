import { describe, expect, it } from 'vitest';
import { cutBars } from './reviewCut';
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
});
