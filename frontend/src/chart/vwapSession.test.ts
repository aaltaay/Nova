import { describe, expect, it } from 'vitest';
import {
  coversSessionOpen,
  sampleVwapOntoBars,
  sessionVwapPoints,
} from './vwapSession';
import type { IndicatorBar } from '../chartIndicators';

/** Bar times are ET wall clock encoded as an epoch -- build them the same way. */
function etTime(
  year: number,
  monthIndex: number,
  day: number,
  hour: number,
  minute: number,
  second = 0,
): number {
  return Date.UTC(year, monthIndex, day, hour, minute, second) / 1000;
}

function bar(time: number, price: number, volume: number): IndicatorBar {
  return {
    time,
    open: price,
    high: price + 0.1,
    low: price - 0.1,
    close: price,
    volume,
  };
}

/** Minutes 09:30.. of one RTH session, prices and volumes both varying. */
function rthMinutes(count: number, day = 25): IndicatorBar[] {
  const out: IndicatorBar[] = [];
  for (let i = 0; i < count; i += 1) {
    out.push(
      bar(
        etTime(2026, 7, day, 9, 30 + i),
        10 + (i % 7) * 0.25,
        1_000 + i * 137,
      ),
    );
  }
  return out;
}

/** Aggregate 1Min into N-minute pane bars, the way the backend derives them. */
function aggregate(minuteBars: IndicatorBar[], minutes: number): IndicatorBar[] {
  const bucket = minutes * 60;
  const byKey = new Map<number, IndicatorBar>();
  const out: IndicatorBar[] = [];
  for (const b of minuteBars) {
    const key = Math.floor(b.time / bucket) * bucket;
    const current = byKey.get(key);
    if (!current) {
      const next = { ...b, time: key };
      byKey.set(key, next);
      out.push(next);
      continue;
    }
    current.high = Math.max(current.high, b.high);
    current.low = Math.min(current.low, b.low);
    current.close = b.close;
    current.volume += b.volume;
  }
  return out;
}

/** Split each minute into six 10-second pane bars. */
function tenSecondBars(minuteBars: IndicatorBar[]): IndicatorBar[] {
  const out: IndicatorBar[] = [];
  for (const b of minuteBars) {
    for (let s = 0; s < 60; s += 10) {
      out.push({ ...b, time: b.time + s });
    }
  }
  return out;
}

function valueAt(line: Array<{ time: unknown; value: number }>, time: number): number | undefined {
  return line.find((p) => p.time === time)?.value;
}

describe('sessionVwapPoints', () => {
  it('anchors at the 09:30 ET open and ignores premarket volume', () => {
    const bars = [
      bar(etTime(2026, 7, 25, 4, 0), 50, 100_000),
      bar(etTime(2026, 7, 25, 9, 29), 50, 100_000),
      bar(etTime(2026, 7, 25, 9, 30), 10, 1_000),
      bar(etTime(2026, 7, 25, 9, 31), 10, 1_000),
    ];
    const points = sessionVwapPoints(bars);

    expect(points).toHaveLength(2);
    expect(points[0].time).toBe(etTime(2026, 7, 25, 9, 30));
    // hlc3 of a flat 10.0 bar; the 50.00 premarket prints contributed nothing.
    expect(points[0].value).toBeCloseTo(10, 10);
    expect(points[1].value).toBeCloseTo(10, 10);
  });

  it('weights by volume rather than averaging bars', () => {
    const bars = [
      bar(etTime(2026, 7, 25, 9, 30), 10, 1_000),
      bar(etTime(2026, 7, 25, 9, 31), 20, 3_000),
    ];
    const points = sessionVwapPoints(bars);
    // (10*1000 + 20*3000) / 4000 = 17.5, not the 15.0 a simple mean would give.
    expect(points[1].value).toBeCloseTo(17.5, 10);
  });

  it('carries the previous value through a zero-volume minute', () => {
    const bars = [
      bar(etTime(2026, 7, 25, 9, 30), 10, 1_000),
      bar(etTime(2026, 7, 25, 9, 31), 99, 0),
      bar(etTime(2026, 7, 25, 9, 32), 10, 1_000),
    ];
    const points = sessionVwapPoints(bars);

    expect(points).toHaveLength(3);
    expect(points[1].value).toBeCloseTo(points[0].value, 10);
    expect(points[1].value).toBeCloseTo(10, 10);
  });

  it('stops accumulating at the 16:00 ET close and carries the final value', () => {
    const bars = [
      bar(etTime(2026, 7, 25, 9, 30), 10, 1_000),
      bar(etTime(2026, 7, 25, 15, 59), 10, 1_000),
      bar(etTime(2026, 7, 25, 16, 0), 500, 5_000_000),
      bar(etTime(2026, 7, 25, 19, 59), 500, 5_000_000),
    ];
    const points = sessionVwapPoints(bars);

    expect(points).toHaveLength(4);
    expect(points[3].value).toBeCloseTo(points[1].value, 10);
    expect(points[3].value).toBeCloseTo(10, 10);
  });

  it('resets the accumulator on each ET session', () => {
    const bars = [
      bar(etTime(2026, 7, 25, 9, 30), 100, 1_000),
      bar(etTime(2026, 7, 25, 9, 31), 100, 1_000),
      bar(etTime(2026, 7, 26, 9, 30), 10, 1_000),
      bar(etTime(2026, 7, 26, 9, 31), 10, 1_000),
    ];
    const points = sessionVwapPoints(bars);

    expect(points[1].value).toBeCloseTo(100, 10);
    // Day two starts clean instead of dragging day one's 100.00 forward.
    expect(points[2].value).toBeCloseTo(10, 10);
  });

  it('anchors at 09:30 ET on both DST transition weeks', () => {
    for (const [monthIndex, day] of [[2, 9], [10, 2]] as const) {
      const bars = [
        bar(etTime(2026, monthIndex, day, 9, 29), 99, 500_000),
        bar(etTime(2026, monthIndex, day, 9, 30), 10, 1_000),
      ];
      const points = sessionVwapPoints(bars);
      expect(points).toHaveLength(1);
      expect(points[0].value).toBeCloseTo(10, 10);
    }
  });

  it('returns nothing before the open', () => {
    const premarketOnly = [
      bar(etTime(2026, 7, 25, 4, 0), 10, 1_000),
      bar(etTime(2026, 7, 25, 8, 15), 11, 2_000),
    ];
    expect(sessionVwapPoints(premarketOnly)).toEqual([]);
    expect(sessionVwapPoints([])).toEqual([]);
  });
});

describe('sampleVwapOntoBars', () => {
  it('gives every timeframe the same VWAP at a shared bar close', () => {
    const minutes = rthMinutes(30);
    const points = sessionVwapPoints(minutes);

    const oneMin = sampleVwapOntoBars(points, minutes, '1Min');
    const fiveMin = sampleVwapOntoBars(points, aggregate(minutes, 5), '5Min');
    const fifteenMin = sampleVwapOntoBars(points, aggregate(minutes, 15), '15Min');

    // The 09:30 5-minute bar closes with the 09:34 minute; the 09:30 15-minute
    // bar closes with the 09:44 minute. Same series, so the values must match.
    expect(valueAt(fiveMin, etTime(2026, 7, 25, 9, 30)))
      .toBeCloseTo(valueAt(oneMin, etTime(2026, 7, 25, 9, 34))!, 10);
    expect(valueAt(fifteenMin, etTime(2026, 7, 25, 9, 30)))
      .toBeCloseTo(valueAt(oneMin, etTime(2026, 7, 25, 9, 44))!, 10);
    expect(valueAt(fifteenMin, etTime(2026, 7, 25, 9, 45)))
      .toBeCloseTo(valueAt(oneMin, etTime(2026, 7, 25, 9, 59))!, 10);

    // Session close is identical on all three (the old per-pane math drifted here).
    expect(fiveMin.at(-1)!.value).toBeCloseTo(oneMin.at(-1)!.value, 10);
    expect(fifteenMin.at(-1)!.value).toBeCloseTo(oneMin.at(-1)!.value, 10);
  });

  it('steps a 10Sec pane once per source minute', () => {
    const minutes = rthMinutes(5);
    const points = sessionVwapPoints(minutes);

    const tenSec = sampleVwapOntoBars(points, tenSecondBars(minutes), '10Sec');
    const oneMin = sampleVwapOntoBars(points, minutes, '1Min');

    const minuteStart = etTime(2026, 7, 25, 9, 32);
    const expected = valueAt(oneMin, minuteStart)!;
    for (let s = 0; s < 60; s += 10) {
      expect(valueAt(tenSec, minuteStart + s)).toBeCloseTo(expected, 10);
    }
    expect(valueAt(tenSec, etTime(2026, 7, 25, 9, 33))).not.toBeCloseTo(expected, 6);
  });

  it('draws nothing on a pane bar before the open', () => {
    const minutes = rthMinutes(5);
    const points = sessionVwapPoints(minutes);
    const paneBars = [bar(etTime(2026, 7, 25, 8, 0), 10, 1_000), ...minutes];

    const line = sampleVwapOntoBars(points, paneBars, '1Min');
    expect(valueAt(line, etTime(2026, 7, 25, 8, 0))).toBeUndefined();
    expect(line).toHaveLength(minutes.length);
  });

  it('does not bleed one session into the next premarket', () => {
    const points = sessionVwapPoints([
      ...rthMinutes(5, 25),
      ...rthMinutes(5, 26),
    ]);
    const paneBars = [
      ...rthMinutes(5, 25),
      bar(etTime(2026, 7, 26, 5, 0), 10, 1_000),
      ...rthMinutes(5, 26),
    ];

    const line = sampleVwapOntoBars(points, paneBars, '1Min');
    expect(valueAt(line, etTime(2026, 7, 26, 5, 0))).toBeUndefined();
    expect(valueAt(line, etTime(2026, 7, 26, 9, 30))).toBeDefined();
  });

  it('returns nothing for daily and above', () => {
    const minutes = rthMinutes(10);
    const points = sessionVwapPoints(minutes);
    for (const tf of ['1Day', '1Week', '1Month']) {
      expect(sampleVwapOntoBars(points, minutes, tf)).toEqual([]);
    }
  });

  it('returns nothing when either side is empty', () => {
    expect(sampleVwapOntoBars([], rthMinutes(3), '1Min')).toEqual([]);
    expect(sampleVwapOntoBars(sessionVwapPoints(rthMinutes(3)), [], '1Min')).toEqual([]);
  });
});

describe('coversSessionOpen', () => {
  it('is true when the source reaches the open', () => {
    expect(coversSessionOpen(rthMinutes(10))).toBe(true);
    expect(coversSessionOpen([
      bar(etTime(2026, 7, 25, 4, 0), 10, 1_000),
      ...rthMinutes(10),
    ])).toBe(true);
  });

  it('is false when the window starts mid-session', () => {
    const late = [
      bar(etTime(2026, 7, 25, 13, 15), 10, 1_000),
      bar(etTime(2026, 7, 25, 13, 16), 10, 1_000),
    ];
    expect(coversSessionOpen(late)).toBe(false);
  });

  it('only judges the newest ET day', () => {
    // Yesterday is complete, today starts late -- today is what gets drawn.
    expect(coversSessionOpen([
      ...rthMinutes(10, 25),
      bar(etTime(2026, 7, 26, 11, 0), 10, 1_000),
    ])).toBe(false);
  });

  it('is false with no usable bars', () => {
    expect(coversSessionOpen([])).toBe(false);
  });
});
