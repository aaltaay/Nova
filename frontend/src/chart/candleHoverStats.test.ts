import { describe, expect, it } from 'vitest';
import type { IndicatorBar } from '../chartIndicators';
import {
  candleClockLabel,
  candleDayLabel,
  candleEpoch,
  candleSession,
  candleShape,
  closeInRangeLabel,
  dayVolumeThrough,
  dollarsTraded,
  regularOpenOf,
  timeframeLabel,
  volumeVsAverage,
  vwapAtClose,
} from './candleHoverStats';

/** An ET wall-clock minute on 2026-10-12 as the chart's epoch (ET read as UTC). */
const et = (h: number, m: number, s = 0, day = 12) => Date.UTC(2026, 9, day, h, m, s) / 1000;
const bar = (time: number, open: number, volume: number, close = open): IndicatorBar =>
  ({ time, open, high: Math.max(open, close), low: Math.min(open, close), close, volume });

describe('candleShape', () => {
  it('measures the move, the range, where it closed and the wicks', () => {
    const s = candleShape({ open: 2.81, high: 3.05, low: 2.78, close: 3.0 });
    expect(s.change).toBeCloseTo(0.19);
    expect(s.changeFrac).toBeCloseTo(0.19 / 2.81);
    expect(s.range).toBeCloseTo(0.27);
    expect(s.rangeFrac).toBeCloseTo(0.27 / 2.78);
    expect(s.closeInRange).toBeCloseTo(0.22 / 0.27);
    expect(s.upperWick).toBeCloseTo(0.05);
    expect(s.lowerWick).toBeCloseTo(0.03);
  });

  it('has no place in the range for a candle with no range', () => {
    expect(candleShape({ open: 1, high: 1, low: 1, close: 1 }).closeInRange).toBeNull();
  });
});

describe('closeInRangeLabel', () => {
  it('reads from the nearer end', () => {
    expect(closeInRangeLabel(0.81)).toBe('top 19%');
    expect(closeInRangeLabel(0.08)).toBe('bottom 8%');
    expect(closeInRangeLabel(1)).toBe('at the high');
    expect(closeInRangeLabel(0)).toBe('at the low');
    expect(closeInRangeLabel(null)).toBeNull();
  });
});

describe('volumeVsAverage', () => {
  it('compares with the average of the candles before', () => {
    expect(volumeVsAverage(300, [100, 200, 300])).toEqual({ average: 200, multiple: 1.5, count: 3 });
  });

  it('is absent without a volume or candles before it', () => {
    expect(volumeVsAverage(null, [100])).toBeNull();
    expect(volumeVsAverage(100, [])).toBeNull();
    expect(volumeVsAverage(100, [0, 0])).toBeNull();
  });
});

describe('dollarsTraded', () => {
  it('is shares times the typical price', () => {
    expect(dollarsTraded(1000, { open: 1, high: 3, low: 1, close: 2 })).toBeCloseTo(2000);
    expect(dollarsTraded(0, { open: 1, high: 1, low: 1, close: 1 })).toBeNull();
  });
});

describe('dayVolumeThrough', () => {
  const day = [bar(et(4, 0), 1, 10), bar(et(9, 30), 2, 100), bar(et(9, 41), 3, 1000), bar(et(9, 42), 3, 5000)];

  it('sums the session from 04:00 through the candle', () => {
    expect(dayVolumeThrough(day, et(9, 41), et(9, 42))).toEqual({ volume: 1110, fromOpen: true });
  });

  it('leaves out yesterday and says when the bars start late', () => {
    const late = [bar(et(15, 0, 0, 9), 1, 999), bar(et(7, 0), 1, 10), bar(et(9, 41), 3, 1000)];
    expect(dayVolumeThrough(late, et(9, 41), et(9, 42))).toEqual({ volume: 1010, fromOpen: false });
  });

  it('is absent when the bars stop before the candle', () => {
    expect(dayVolumeThrough(day.slice(0, 2), et(9, 41), et(9, 42))).toBeNull();
  });
});

describe('vwapAtClose', () => {
  it('takes the newest point before the close on the candle\'s day', () => {
    const points = [
      { time: et(15, 59, 0, 9), value: 9 },
      { time: et(9, 40), value: 2.3 },
      { time: et(9, 41), value: 2.34 },
      { time: et(9, 42), value: 2.4 },
    ];
    expect(vwapAtClose(points, et(9, 41), et(9, 42))).toBe(2.34);
    expect(vwapAtClose(points.slice(0, 1), et(9, 41), et(9, 42))).toBeNull();
  });
});

describe('regularOpenOf', () => {
  const day = [bar(et(9, 29), 1.9, 1), bar(et(9, 30), 1.95, 1), bar(et(9, 31), 2.05, 1)];

  it('is the open of the 9:30 minute', () => {
    expect(regularOpenOf(day, et(9, 41))).toBe(1.95);
  });

  it('is absent for a premarket candle or a 9:30 minute with no bar', () => {
    expect(regularOpenOf(day, et(9, 15))).toBeNull();
    expect(regularOpenOf([day[0], day[2]], et(9, 41))).toBeNull();
  });
});

describe('labels', () => {
  it('names the session, the timeframe, the day and the clock', () => {
    expect(candleSession(et(8, 0)).label).toBe('Premarket');
    expect(candleSession(et(9, 41)).label).toBe('Regular hours');
    expect(candleSession(et(17, 0)).label).toBe('After hours');
    expect(timeframeLabel('10Sec')).toBe('10 sec');
    expect(timeframeLabel('1Min')).toBe('1 min');
    expect(timeframeLabel('1Day')).toBe('1 day');
    expect(candleDayLabel(et(9, 41))).toBe('Oct 12');
    expect(candleClockLabel(et(9, 41), 60, false)).toBe('9:41 AM – 9:42 AM');
    expect(candleClockLabel(et(9, 41, 20), 10, true)).toBe('9:41:20 AM – 9:41:30 AM');
  });

  it('reads a daily candle\'s time in every form the chart reports it', () => {
    const day = Date.UTC(2026, 9, 12) / 1000;
    expect(candleEpoch('2026-10-12')).toBe(day);
    expect(candleEpoch({ year: 2026, month: 10, day: 12 })).toBe(day);
    expect(candleEpoch(et(9, 41) as never)).toBe(et(9, 41));
  });
});
