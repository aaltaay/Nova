import { describe, expect, it } from 'vitest';
import {
  coversSessionOpen,
  paneSessionBehindLabel,
  sampleVwapOntoBars,
  sessionVwapPoints,
  vwapSourceForPane,
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

function valueAt(
  line: Array<{ time: unknown; value?: number }>,
  time: number,
): number | undefined {
  const point = line.find((p) => p.time === time);
  return typeof point?.value === 'number' && Number.isFinite(point.value)
    ? point.value
    : undefined;
}

function valued(
  line: Array<{ time: unknown; value?: number }>,
): Array<{ time: unknown; value: number }> {
  return line.filter(
    (p): p is { time: unknown; value: number } => (
      typeof p.value === 'number' && Number.isFinite(p.value)
    ),
  );
}

function etDay(time: number): number {
  const d = new Date(time * 1000);
  return d.getUTCFullYear() * 10_000 + d.getUTCMonth() * 100 + d.getUTCDate();
}

describe('sessionVwapPoints', () => {
  it('anchors at the 04:00 ET premarket open and includes that volume', () => {
    const bars = [
      bar(etTime(2026, 7, 25, 3, 59), 50, 100_000),
      bar(etTime(2026, 7, 25, 4, 0), 10, 1_000),
      bar(etTime(2026, 7, 25, 4, 1), 10, 1_000),
    ];
    const points = sessionVwapPoints(bars);

    expect(points).toHaveLength(2);
    expect(points[0].time).toBe(etTime(2026, 7, 25, 4, 0));
    // 03:59 is still yesterday's leftover window -- it must not pull VWAP to 50.
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

  it('moves the tip when a live 1Min overlay minute has stamped volume', () => {
    const open = etTime(2026, 7, 25, 9, 30);
    const hist = [
      bar(open, 10, 1_000),
      bar(open + 60, 10, 1_000),
    ];
    const overlayZero = [...hist, bar(open + 120, 20, 0)];
    const overlayLive = [...hist, bar(open + 120, 20, 2_000)];

    const stale = sessionVwapPoints(overlayZero);
    const fresh = sessionVwapPoints(overlayLive);

    expect(stale.at(-1)?.value).toBeCloseTo(10, 10);
    expect(fresh.at(-1)?.value).toBeCloseTo(15, 10);
  });

  it('resets at 16:00 ET so after-hours volume starts a new VWAP', () => {
    // LABT-shaped: dead RTH then a huge AH print. Mixing those volumes would
    // erase the daytime decision level (D-007). Webull/DAS start a new session.
    const bars = [
      bar(etTime(2026, 7, 25, 9, 30), 10, 1_000),
      bar(etTime(2026, 7, 25, 15, 59), 10, 1_000),
      bar(etTime(2026, 7, 25, 16, 0), 500, 5_000_000),
      bar(etTime(2026, 7, 25, 19, 59), 500, 5_000_000),
    ];
    const points = sessionVwapPoints(bars);

    expect(points).toHaveLength(4);
    expect(points[1].value).toBeCloseTo(10, 10);
    expect(points[2].value).toBeCloseTo(500, 0);
    expect(points[3].value).toBeCloseTo(500, 0);
    expect(points[3].value).not.toBeCloseTo(points[1].value, 1);
  });

  it('stops accumulating at the 20:00 ET after-hours end and carries that value', () => {
    const bars = [
      bar(etTime(2026, 7, 25, 16, 0), 10, 1_000),
      bar(etTime(2026, 7, 25, 19, 59), 10, 1_000),
      bar(etTime(2026, 7, 25, 20, 0), 500, 5_000_000),
      bar(etTime(2026, 7, 25, 21, 50), 500, 5_000_000),
    ];
    const points = sessionVwapPoints(bars);

    expect(points).toHaveLength(4);
    expect(points[1].value).toBeCloseTo(10, 10);
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

  it('anchors at 04:00 ET on both DST transition weeks', () => {
    for (const [monthIndex, day] of [[2, 9], [10, 2]] as const) {
      const bars = [
        bar(etTime(2026, monthIndex, day, 3, 59), 99, 500_000),
        bar(etTime(2026, monthIndex, day, 4, 0), 10, 1_000),
      ];
      const points = sessionVwapPoints(bars);
      expect(points).toHaveLength(1);
      expect(points[0].value).toBeCloseTo(10, 10);
    }
  });

  it('returns nothing before the premarket open', () => {
    const overnightOnly = [
      bar(etTime(2026, 7, 25, 0, 30), 10, 1_000),
      bar(etTime(2026, 7, 25, 3, 59), 11, 2_000),
    ];
    expect(sessionVwapPoints(overnightOnly)).toEqual([]);
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

  it('walks a 10Sec pane with each painted bar instead of once per minute', () => {
    const open = etTime(2026, 7, 25, 9, 30);
    const minutes = [bar(open, 10, 1_000), bar(open + 60, 10, 1_000)];
    const tenSec: IndicatorBar[] = [];
    for (let s = 0; s < 120; s += 10) {
      tenSec.push(bar(open + s, 10 + (s / 10) * 2, 1_000));
    }
    const line = sampleVwapOntoBars(
      sessionVwapPoints(vwapSourceForPane(minutes, tenSec, '10Sec')),
      tenSec,
      '10Sec',
    );

    expect(line).toHaveLength(tenSec.length);
    expect(valueAt(line, open + 50)).not.toBeCloseTo(valueAt(line, open)!, 6);
    expect(valueAt(line, open + 60)).not.toBeCloseTo(valueAt(line, open + 50)!, 6);
  });

  it('extends onto a live tip the store has not painted yet', () => {
    const minutes = rthMinutes(3);
    const line = sampleVwapOntoBars(
      sessionVwapPoints(minutes),
      minutes,
      '1Min',
      { extendToTime: etTime(2026, 7, 25, 9, 33) },
    );

    expect(line.at(-1)!.time).toBe(etTime(2026, 7, 25, 9, 33));
    expect(line.at(-1)!.value).toBeCloseTo(line.at(-2)!.value, 10);
  });

  it('draws nothing on a pane bar before the premarket open', () => {
    const minutes = rthMinutes(5);
    const points = sessionVwapPoints(minutes);
    const paneBars = [bar(etTime(2026, 7, 25, 3, 0), 10, 1_000), ...minutes];

    const line = sampleVwapOntoBars(points, paneBars, '1Min');
    expect(valueAt(line, etTime(2026, 7, 25, 3, 0))).toBeUndefined();
    expect(valued(line)).toHaveLength(minutes.length);
  });

  it('paints the after-hours VWAP on a same-day pane, not the frozen 16:00 value', () => {
    const pane = [
      bar(etTime(2026, 7, 27, 15, 59), 2.18, 1_495),
      bar(etTime(2026, 7, 27, 16, 0), 3.20, 50_000),
      bar(etTime(2026, 7, 27, 16, 1), 3.20, 50_000),
    ];
    const line = sampleVwapOntoBars(sessionVwapPoints(pane), pane, '1Min');
    expect(valueAt(line, etTime(2026, 7, 27, 15, 59))).toBeCloseTo(2.18, 1);
    expect(valueAt(line, etTime(2026, 7, 27, 16, 1)))
      .toBeCloseTo(3.20, 1);
    expect(valueAt(line, etTime(2026, 7, 27, 16, 1)))
      .not.toBeCloseTo(valueAt(line, etTime(2026, 7, 27, 15, 59))!, 1);
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

  it('does not paint yesterday leftover through overnight into the open', () => {
    // AEMD-shaped 1Min window: after-hours leftover, a 15M-share premarket,
    // then the 09:30 print. LineSeries connects adjacent valued points, so a
    // leftover $2.25 sitting next to today's $2.91 becomes a fake diagonal.
    const pane = [
      bar(etTime(2026, 7, 27, 15, 59), 2.18, 1_495),
      bar(etTime(2026, 7, 27, 16, 0), 2.26, 2_271),
      bar(etTime(2026, 7, 27, 21, 50), 3.20, 0),
      bar(etTime(2026, 7, 27, 23, 59), 3.23, 0),
      bar(etTime(2026, 7, 28, 4, 0), 3.23, 10_000),
      bar(etTime(2026, 7, 28, 7, 0), 3.82, 377_534),
      bar(etTime(2026, 7, 28, 9, 29), 2.90, 85_297),
      bar(etTime(2026, 7, 28, 9, 30), 2.95, 260_670),
      bar(etTime(2026, 7, 28, 9, 31), 2.97, 50_000),
    ];
    const line = sampleVwapOntoBars(sessionVwapPoints(pane), pane, '1Min');
    const painted = valued(line);

    expect(valueAt(line, etTime(2026, 7, 27, 21, 50))).toBeUndefined();
    expect(valueAt(line, etTime(2026, 7, 28, 4, 0))).toBeDefined();
    expect(valueAt(line, etTime(2026, 7, 28, 7, 0))).toBeDefined();
    expect(valueAt(line, etTime(2026, 7, 28, 9, 29))).toBeDefined();
    expect(valueAt(line, etTime(2026, 7, 28, 9, 30))).toBeDefined();
    expect(painted.length).toBe(5);
    expect(painted.every((p) => etDay(p.time as number) === etDay(etTime(2026, 7, 28, 9, 30)))).toBe(true);
    for (let i = 1; i < painted.length; i += 1) {
      expect(etDay(painted[i].time as number)).toBe(etDay(painted[i - 1].time as number));
    }
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

describe('vwapSourceForPane', () => {
  it('keeps 1Min bars from before the 10Sec window so the 04:00 anchor survives', () => {
    const minutes = [
      bar(etTime(2026, 7, 25, 4, 0), 10, 1_000),
      ...rthMinutes(90),
    ];
    const paneStart = etTime(2026, 7, 25, 10, 0);
    const pane = tenSecondBars(minutes.filter((b) => b.time >= paneStart));
    const source = vwapSourceForPane(minutes, pane, '10Sec');

    expect(source[0].time).toBe(etTime(2026, 7, 25, 4, 0));
    const overlap = source.filter((b) => b.time >= paneStart);
    expect(overlap.some((b) => b.time === paneStart + 10)).toBe(true);
    expect(overlap.every((b) => pane.some((p) => p.time === b.time))).toBe(true);
  });

  it('leaves a 1Min pane on the 1Min source', () => {
    const minutes = rthMinutes(10);
    expect(vwapSourceForPane(minutes, minutes, '1Min')).toBe(minutes);
  });
});

describe('coversSessionOpen', () => {
  it('is true when the source reaches the 04:00 open', () => {
    expect(coversSessionOpen(rthMinutes(10))).toBe(false);
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

describe('paneSessionBehindLabel (QA R28)', () => {
  const today = [bar(etTime(2026, 8, 22, 5, 5), 1.35, 1_000), bar(etTime(2026, 8, 22, 5, 6), 1.5, 1_000)];
  const yesterdayEvening = [bar(etTime(2026, 8, 21, 19, 55), 1.2, 1_000)];

  it("names the pane's session when its bars end on an earlier day than the source", () => {
    expect(paneSessionBehindLabel(today, yesterdayEvening)).toBe('Sep 21');
  });

  it('is null when the pane is on the same session, ahead, or unknown', () => {
    expect(paneSessionBehindLabel(today, today)).toBeNull();
    expect(paneSessionBehindLabel(yesterdayEvening, today)).toBeNull();
    expect(paneSessionBehindLabel([], yesterdayEvening)).toBeNull();
    expect(paneSessionBehindLabel(today, [])).toBeNull();
  });
});
