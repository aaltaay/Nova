import { describe, expect, it } from 'vitest';
import { TREND_COLORS } from '../stock_read';
import { etChartSeconds } from '../tickerChartData';
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import {
  candlesSince,
  chartHhmm,
  chartSec,
  chartToEpoch,
  contiguousTail,
  linesToMeet,
  meetTailOk,
  nearestWalls,
  type AheadCandle,
  type AheadLineIn,
  type AheadZoneIn,
} from './aheadGeometry';

/** 09:01 ET on a made-up day, in epoch seconds (EDT). */
const E901 = Date.UTC(2026, 9, 21, 13, 1) / 1000;
const C901 = chartSec(E901);

function candles(n: number, lastClose = 4.62, gapAt: number | null = null): AheadCandle[] {
  const out: AheadCandle[] = [];
  for (let i = n - 1; i >= 0; i -= 1) {
    const extra = gapAt !== null && i >= gapAt ? 60 : 0;
    out.push({ t: C901 - i * 60 - extra, c: lastClose });
  }
  return out;
}

const line = (kind: 'support' | 'resistance', now_p: number, slope: number, now_t = E901, id = kind): AheadLineIn => ({
  id, kind, state: 'holding', now_t, now_p, slope,
});

describe('the clocks', () => {
  it('reads chart seconds as the Eastern wall clock and goes back to epoch seconds', () => {
    expect(chartHhmm(C901)).toBe('09:01');
    expect(chartToEpoch(C901)).toBe(E901);
    const winter = Date.UTC(2026, 11, 1, 14, 30) / 1000;
    expect(chartToEpoch(etChartSeconds(winter * 1000))).toBe(winter);
  });

  it('counts the consecutive minutes at the end, and the candles since a line was read', () => {
    expect(contiguousTail([])).toBe(0);
    expect(contiguousTail(candles(40))).toBe(40);
    expect(contiguousTail(candles(40, 4.62, 5))).toBe(5);
    expect(candlesSince(candles(40), C901 - 120)).toBe(2);
    expect(candlesSince(candles(40), C901 + 60)).toBe(-1);
    expect(meetTailOk(null, candles(30))).toBe(true);
    expect(meetTailOk(12, candles(40))).toBe(false);
  });

  it("mirrors the stock read's trend-line colours", () => {
    expect(AHEAD_COLORS.support).toBe(TREND_COLORS.support);
    expect(AHEAD_COLORS.resistance).toBe(TREND_COLORS.resistance);
  });
});

describe("Nova's lines carried on to where they meet", () => {
  it('meets where the rising support reaches the falling resistance', () => {
    const r = linesToMeet([line('support', 4.6, 0.01), line('resistance', 4.7, -0.01)], candles(40), true);
    expect(r.state).toBe('meet');
    expect(r.meet?.inCandles).toBeCloseTo(5);
    expect(r.meet?.p).toBeCloseTo(4.65);
    expect(r.meet?.withinZone).toBe(true);
    expect(r.meet?.t).toBe(E901 + 300);
  });

  it('re-anchors a line read a few candles before the newest one', () => {
    const r = linesToMeet(
      [line('support', 4.58, 0.01, E901 - 120), line('resistance', 4.7, -0.01)], candles(40), true,
    );
    expect(r.supportP).toBeCloseTo(4.6);
    expect(r.meet?.inCandles).toBeCloseTo(5);
  });

  it('counts the meet in candles when the stock skips minutes', () => {
    const r = linesToMeet([line('support', 4.6, 0.01), line('resistance', 4.7, -0.01)], candles(40, 4.62, 3), false);
    expect(r.meet?.t).toBeNull();
    expect(r.meet?.inCandles).toBeCloseTo(5);
  });

  it('says when the meet lies past the zone', () => {
    const r = linesToMeet([line('support', 4.6, 0.001), line('resistance', 4.7, -0.001)], candles(40), true);
    expect(r.meet?.inCandles).toBeCloseTo(50);
    expect(r.meet?.withinZone).toBe(false);
  });

  it('picks the support nearest under the price and the resistance nearest over it, holding lines only', () => {
    const r = linesToMeet([
      line('support', 4.5, 0.01, E901, 's-low'), line('support', 4.61, 0.01, E901, 's-near'),
      line('support', 4.7, 0.01, E901, 's-over'), line('resistance', 4.9, -0.01, E901, 'r-far'),
      line('resistance', 4.65, -0.01, E901, 'r-near'), { ...line('resistance', 4.63, -0.01), id: 'r-broken', state: 'broken' },
    ], candles(40), true);
    expect([r.supportId, r.resistanceId]).toEqual(['s-near', 'r-near']);
  });

  it('says why when there is nothing to carry on', () => {
    expect(linesToMeet([], candles(40), true).reason).toBe(AHEAD_WORDS.linesNone);
    expect(linesToMeet([line('resistance', 4.7, -0.01)], candles(40), true).reason).toBe(AHEAD_WORDS.linesNoSupport);
    expect(linesToMeet([line('support', 4.6, 0.01)], candles(40), true).reason).toBe(AHEAD_WORDS.linesNoResistance);
    expect(linesToMeet([line('support', 4.6, 0.01)], [], true).reason).toBe(AHEAD_WORDS.noCandles);
    const met = linesToMeet([line('support', 4.62, 0.01), line('resistance', 4.62, -0.01)], candles(40), true);
    expect(met.state).toBe('past');
    expect(met.reason).toBe(AHEAD_WORDS.linesMet);
  });

  it('says the lines met behind the newest candle when the rising support is carried over the falling resistance', () => {
    // Read 10 candles ago: support 4.50 +0.02 a candle is 4.70 now, resistance 4.75 -0.02 is 4.55 now (close 4.62).
    const old = E901 - 600;
    const r = linesToMeet([line('support', 4.5, 0.02, old), line('resistance', 4.75, -0.02, old)], candles(40), true);
    expect(r.state).toBe('past');
    expect(r.reason).toBe(AHEAD_WORDS.linesMet);
    expect([r.supportId, r.resistanceId]).toEqual(['support', 'resistance']);
    expect(r.supportP).toBeCloseTo(4.7);
    expect(r.resistanceP).toBeCloseTo(4.55);
    expect(r.meet).toBeNull();
  });
});

describe('the walls', () => {
  const zone = (id: string, lo: number, hi: number, kinds: string[]): AheadZoneIn => ({
    id, lo, hi, label: `${lo.toFixed(2)} · ${kinds.join(' · ')}`, members: kinds.map((kind) => ({ kind })),
  });

  it('takes the nearest zone from the candles each side, skipping round numbers, VWAP and the zone at the price', () => {
    const w = nearestWalls([
      zone('a', 4.84, 4.85, ['top']), zone('b', 4.7, 4.7, ['half']), zone('c', 4.66, 4.67, ['vwap']),
      zone('d', 4.6, 4.64, ['top']), zone('e', 4.5, 4.5, ['bottom', 'half']), zone('f', 4.3, 4.31, ['lod']),
    ], 4.62);
    expect(w.above).toEqual({ zoneId: 'a', price: 4.84, label: '4.84 · top' });
    expect(w.below).toEqual({ zoneId: 'e', price: 4.5, label: '4.50 · bottom · half' });
    expect(w.reason).toBeNull();
  });

  it('says why with no wall', () => {
    expect(nearestWalls([zone('b', 4.7, 4.7, ['whole'])], 4.62)).toEqual({ above: null, below: null, reason: AHEAD_WORDS.noWalls });
  });
});
