import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import type { SerializedDrawing } from 'lightweight-charts-drawing';
import {
  buildSeriesTimeIndex,
  nearestSeriesTime,
  isPriceOnlyDrawing,
  snapDrawingToSeries,
  toCanonicalTime,
  toStorableDrawing,
} from './chartDrawingTime';

/** 2026-08-26 09:30, 09:31, 09:32 ET read through UTC getters. */
const MIN_0930 = Math.floor(Date.UTC(2026, 7, 26, 9, 30) / 1000);
const MIN_0931 = MIN_0930 + 60;
const MIN_0932 = MIN_0930 + 120;

const INTRADAY_TIMES: Time[] = [MIN_0930, MIN_0931, MIN_0932] as Time[];
const DAILY_TIMES: Time[] = ['2026-08-24', '2026-08-25', '2026-08-26'] as Time[];

function drawing(type: string, anchors: Array<{ time: Time; price: number }>): SerializedDrawing {
  return { id: `${type}-1`, type, anchors, style: {}, options: {} } as SerializedDrawing;
}

describe('toCanonicalTime', () => {
  it('passes numeric series times through', () => {
    expect(toCanonicalTime(MIN_0931 as Time)).toBe(MIN_0931);
  });

  it('converts a business-day string to UTC midnight epoch seconds', () => {
    expect(toCanonicalTime('2026-08-26' as Time)).toBe(
      Math.floor(Date.UTC(2026, 7, 26) / 1000),
    );
  });

  it('converts a BusinessDay object', () => {
    expect(toCanonicalTime({ year: 2026, month: 8, day: 26 } as unknown as Time)).toBe(
      Math.floor(Date.UTC(2026, 7, 26) / 1000),
    );
  });

  it('returns NaN for unusable input', () => {
    expect(Number.isNaN(toCanonicalTime(null))).toBe(true);
    expect(Number.isNaN(toCanonicalTime(Number.NaN as unknown as Time))).toBe(true);
  });
});

describe('nearestSeriesTime', () => {
  const index = buildSeriesTimeIndex(INTRADAY_TIMES);

  it('returns the exact bar when the anchor matches one', () => {
    expect(nearestSeriesTime(index, MIN_0931)).toBe(MIN_0931);
  });

  it('rounds to the closer neighbour', () => {
    expect(nearestSeriesTime(index, MIN_0930 + 20)).toBe(MIN_0930);
    expect(nearestSeriesTime(index, MIN_0930 + 40)).toBe(MIN_0931);
  });

  it('clamps an anchor older than the first bar to the first bar', () => {
    expect(nearestSeriesTime(index, MIN_0930 - 86_400)).toBe(MIN_0930);
  });

  it('clamps an anchor newer than the last bar to the last bar', () => {
    expect(nearestSeriesTime(index, MIN_0932 + 86_400)).toBe(MIN_0932);
  });

  it('returns null when the pane has no bars', () => {
    expect(nearestSeriesTime(buildSeriesTimeIndex([]), MIN_0930)).toBeNull();
  });
});

describe('buildSeriesTimeIndex', () => {
  it('drops times it cannot canonicalize', () => {
    const index = buildSeriesTimeIndex([MIN_0930, 'not-a-date', MIN_0931] as Time[]);
    expect(index.times).toEqual([MIN_0930, MIN_0931]);
    expect(index.canonical).toEqual([MIN_0930, MIN_0931]);
  });
});

describe('snapDrawingToSeries', () => {
  it('maps a 1Min anchor onto a daily business-day string', () => {
    const snapped = snapDrawingToSeries(
      drawing('trend-line', [
        { time: MIN_0930 as Time, price: 10 },
        { time: MIN_0932 as Time, price: 12 },
      ]),
      buildSeriesTimeIndex(DAILY_TIMES),
    );
    expect(snapped.anchors.map((a) => a.time)).toEqual(['2026-08-26', '2026-08-26']);
    expect(snapped.anchors.map((a) => a.price)).toEqual([10, 12]);
  });

  it('maps a daily anchor back onto an intraday numeric grid', () => {
    const snapped = snapDrawingToSeries(
      drawing('vertical-line', [{ time: '2026-08-26' as Time, price: 5 }]),
      buildSeriesTimeIndex(INTRADAY_TIMES),
    );
    // Midnight is before every bar, so it clamps to the session's first bar.
    expect(snapped.anchors[0].time).toBe(MIN_0930);
  });

  it('leaves the drawing untouched when the pane has no bars yet', () => {
    const original = drawing('horizontal-line', [{ time: MIN_0930 as Time, price: 231.5 }]);
    expect(snapDrawingToSeries(original, buildSeriesTimeIndex([]))).toBe(original);
  });

  it('never mutates the input drawing', () => {
    const original = drawing('trend-line', [
      { time: MIN_0930 as Time, price: 10 },
      { time: MIN_0932 as Time, price: 12 },
    ]);
    snapDrawingToSeries(original, buildSeriesTimeIndex(DAILY_TIMES));
    expect(original.anchors[0].time).toBe(MIN_0930);
  });

  it('preserves price on a horizontal line while still snapping its handle', () => {
    const snapped = snapDrawingToSeries(
      drawing('horizontal-line', [{ time: MIN_0930 as Time, price: 231.5 }]),
      buildSeriesTimeIndex(DAILY_TIMES),
    );
    expect(snapped.anchors[0].price).toBe(231.5);
    expect(snapped.anchors[0].time).toBe('2026-08-26');
  });
});

describe('isPriceOnlyDrawing', () => {
  it('knows the horizontal line needs no time scale', () => {
    expect(isPriceOnlyDrawing('horizontal-line')).toBe(true);
    expect(isPriceOnlyDrawing('trend-line')).toBe(false);
  });
});

describe('toStorableDrawing', () => {
  it('collapses a daily business-day anchor to epoch seconds', () => {
    const stored = toStorableDrawing(
      drawing('horizontal-line', [{ time: '2026-08-26' as Time, price: 231.5 }]),
    );
    expect(stored?.anchors[0].time).toBe(Math.floor(Date.UTC(2026, 7, 26) / 1000));
  });

  it('rejects a drawing with an unusable anchor rather than storing NaN', () => {
    expect(
      toStorableDrawing(drawing('trend-line', [{ time: 'nope' as Time, price: 1 }])),
    ).toBeNull();
    expect(
      toStorableDrawing(
        drawing('trend-line', [{ time: MIN_0930 as Time, price: Number.NaN }]),
      ),
    ).toBeNull();
  });
});
