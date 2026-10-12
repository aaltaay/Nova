import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { buildSeriesTimeIndex } from '../chart';
import type { LuldTrail } from '../ibkr';
import { luldAt, luldScene, luldWords } from './luldShapes';

/** 2026-09-22 (EDT, UTC-4): an ET wall-clock time as the chart's candle time, and as the epoch second it happened. */
const chartSec = (hms: string) => Date.parse(`2026-09-22T${hms}Z`) / 1000;
const epoch = (hms: string) => Date.parse(`2026-09-22T${hms}-04:00`) / 1000;

// 1-minute candles 09:30, 09:31, 09:32, then none at 09:33 (no trades), then 09:34.
const INDEX = buildSeriesTimeIndex(['09:30:00', '09:31:00', '09:32:00', '09:34:00'].map(h => chartSec(h) as Time));

function trail(steps: LuldTrail['steps'], extra: Partial<LuldTrail> = {}): LuldTrail {
  return { schema_version: 1, symbol: 'XYZ', source: 'live', state: 'bands', reason: null, tier_sure: true,
    watching_since: epoch('09:30:01'), steps, as_of: epoch('09:34:30'), ...extra };
}

describe('luldAt', () => {
  it('puts a moment inside its candle at its share of the minute', () => {
    expect(luldAt(INDEX, epoch('09:31:15'))).toEqual({ t: chartSec('09:31:00'), frac: 0.25 });
  });

  it('puts a moment in a minute with no candle at the right edge of the candle before it', () => {
    expect(luldAt(INDEX, epoch('09:33:20'))).toEqual({ t: chartSec('09:32:00'), frac: 1 });
  });

  it('starts a moment before the first candle at its left edge, and has nothing without candles', () => {
    expect(luldAt(INDEX, epoch('09:20:00'))).toEqual({ t: chartSec('09:30:00'), frac: 0 });
    expect(luldAt(buildSeriesTimeIndex([]), epoch('09:31:00'))).toBeNull();
  });
});

describe('luldScene', () => {
  it('draws each band from where it began to where the next began, the last to now, and skips a halt', () => {
    const scene = luldScene(trail([
      { ts: epoch('09:30:01'), lower: 9, upper: 11, exact: true },
      { ts: epoch('09:31:30'), lower: 9.14, upper: 11.17, exact: true },
      { ts: epoch('09:32:00'), lower: null, upper: null, exact: false },
      { ts: epoch('09:34:00'), lower: 10.8, upper: 13.2, exact: true },
    ]), INDEX);
    expect(scene?.steps.map(s => [s.from, s.to, s.upper])).toEqual([
      [{ t: chartSec('09:30:00'), frac: 1 / 60 }, { t: chartSec('09:31:00'), frac: 0.5 }, 11],
      [{ t: chartSec('09:31:00'), frac: 0.5 }, { t: chartSec('09:32:00'), frac: 0 }, 11.17],
      [{ t: chartSec('09:34:00'), frac: 0 }, { t: chartSec('09:34:00'), frac: 0.5 }, 13.2],
    ]);
  });

  it('dashes an approximate band and every band whose tier is a guess', () => {
    const steps = [{ ts: epoch('09:30:01'), lower: 9, upper: 11, exact: false }];
    expect(luldScene(trail(steps), INDEX)?.steps[0].approx).toBe(true);
    const exact = [{ ...steps[0], exact: true }];
    expect(luldScene(trail(exact), INDEX)?.steps[0].approx).toBe(false);
    expect(luldScene(trail(exact, { tier_sure: false }), INDEX)?.steps[0].approx).toBe(true);
  });

  it('draws nothing without steps, without candles or with only a halt', () => {
    expect(luldScene(null, INDEX)).toBeNull();
    expect(luldScene(trail([]), INDEX)).toBeNull();
    expect(luldScene(trail([{ ts: epoch('09:31:00'), lower: 9, upper: 11, exact: true }]), buildSeriesTimeIndex([])))
      .toBeNull();
    expect(luldScene(trail([{ ts: epoch('09:31:00'), lower: null, upper: null, exact: false }]), INDEX)).toBeNull();
  });
});

describe('luldWords', () => {
  it('names the band in force at its price, ≈ when approximate', () => {
    const words = luldWords(trail([{ ts: epoch('09:30:01'), lower: 4.4, upper: 6.6, exact: true }]));
    expect(words.map(w => [w.id, w.text, w.price, w.valueWhenOff])).toEqual([
      ['luld-upper', 'LULD ▲ 6.60', 6.6, false],
      ['luld-lower', 'LULD ▼ 4.40', 4.4, false],
    ]);
    const approx = luldWords(trail([{ ts: epoch('09:30:01'), lower: 4.4, upper: 6.6, exact: false }]));
    expect(approx.map(w => w.text)).toEqual(['LULD ▲ ≈6.60', 'LULD ▼ ≈4.40']);
  });

  it('names nothing while no band is in force', () => {
    expect(luldWords(trail([
      { ts: epoch('09:30:01'), lower: 9, upper: 11, exact: true },
      { ts: epoch('09:40:00'), lower: null, upper: null, exact: false },
    ]))).toEqual([]);
    expect(luldWords(null)).toEqual([]);
  });
});
