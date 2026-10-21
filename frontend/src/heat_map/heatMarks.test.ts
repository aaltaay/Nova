/**
 * The heat map's marks (ADR 061 amendment 2026-10-21, approved mockup v4): a ✓ / ✕ only where a line that read as a
 * wall shrank or ended, a run at one price as one chip (traded adds up, pulled shows its biggest and how many times),
 * chips that never overlap or leave the plot, the shares inside the big buy and sell dots (never the grey ones), and a
 * hidden stretch boxed for as long as it held.
 */
import { afterEach, describe, expect, it } from 'vitest';
import type { HeatDot, HeatWindow } from './heatFrame';
import { HEAT_CAP_LOG_BRIGHT, HEAT_CAP_LOG_DIM } from './heatMapConstants';
import { heatDotShares, heatMarkLayout, heatMarkShares, heatWallMin, type HeatMarkGeometry } from './heatMarks';
import { heatOf, noteHeatBook, resetAllHeatForTests } from './heatStore';
import { noteHeatWatch, resetHeatWatchForTests } from './heatWatch';

const T1 = 1792592802.3;   // SPCX 2026-10-21 10:26:42.3 ET, the right edge
const W: HeatWindow = { t0: T1 - 30, t1: T1 };
const capLog = (b: number) => HEAT_CAP_LOG_DIM + (HEAT_CAP_LOG_BRIGHT - HEAT_CAP_LOG_DIM) * (b / 100);
const measure = (text: string) => text.length * 6;
/** 1,000 px for the 30 s window, 20 rows of 20 px from 161.90 (row 0 at the bottom) to 162.09. */
const G: HeatMarkGeometry = {
  X: (t) => ((t - W.t0) / (W.t1 - W.t0)) * 1000,
  Y: (tick) => (16209.5 - tick) * 20,
  plot: { x: 0, y: 0, w: 1000, h: 400 },
  lo: 16190,
  hi: 16209,
};

function drop(ts: number, over: Record<string, unknown> = {}) {
  return { ts, side: 'bid', price: 162.0, pulled: 0, filled: 3719, outcome: 'traded', level_before: 5219,
    on_approach: false, ...over };
}

function feed(drops: Array<Record<string, unknown>>, hidden: Array<Record<string, unknown>> = []) {
  noteHeatBook('SPCX', [{ price: 162.0, size: 5219 }], [{ price: 162.06, size: 105 }], false, W.t0 * 1000);
  noteHeatWatch('SPCX', { schema_version: 1, source: 'live', now: T1, reset: false, watching: true, drops, hidden });
  return heatOf('SPCX')!;
}

const layout = (brightness: number, dots: HeatDot[] = [], top = 1) =>
  heatMarkLayout(heatOf('SPCX')!, W, G, { capLog: capLog(brightness), dots, top }, measure);

afterEach(() => {
  resetAllHeatForTests();
  resetHeatWatchForTests();
});

describe('which walls get a mark', () => {
  it('reads a wall as the ramp\'s yellow: about 9,900 shares at brightness 45, about 3,700 at 85', () => {
    expect(heatWallMin(capLog(45))).toBeGreaterThan(9_000);
    expect(heatWallMin(capLog(45))).toBeLessThan(11_000);
    expect(heatWallMin(capLog(85))).toBeGreaterThan(3_300);
    expect(heatWallMin(capLog(85))).toBeLessThan(4_100);
  });

  it('marks a drop from a line bright enough to read as a wall, and only that', () => {
    feed([drop(T1 - 5), drop(T1 - 12, { level_before: 1200, filled: 900 })]);
    const m = layout(85);
    expect(m.caps).toHaveLength(1);
    expect(m.chips.map((c) => c.text)).toEqual(['✓ 3,719']);
    expect(layout(45).chips).toHaveLength(0);   // 5,219 is not a wall at the default brightness
  });
});

describe('chips', () => {
  it('shows a pulled run as its biggest pull and how many times, and adds a traded run up', () => {
    feed([
      drop(T1 - 26.4, { outcome: 'pulled', pulled: 2000, filled: 0, level_before: 7276 }),
      drop(T1 - 25.5, { outcome: 'pulled', pulled: 2000, filled: 0, level_before: 7275 }),
      drop(T1 - 2.28, { filled: 15004, level_before: 20404 }),
      drop(T1 - 2.27, { filled: 5400, level_before: 5400 }),
    ]);
    expect(layout(85).chips.map((c) => c.text)).toEqual(['✕ 2,000 ×2', '✓ 20.4K']);
  });

  it('puts a bid\'s chip under its line and an ask\'s over it, solid amber when pulled as the price came closer', () => {
    feed([drop(T1 - 20), drop(T1 - 10, { side: 'ask', price: 162.06, outcome: 'pulled', pulled: 6000, filled: 0,
      level_before: 9000, on_approach: true })]);
    const [bid, ask] = layout(85).chips;
    expect(bid.y).toBeGreaterThan(G.Y(16200));
    expect(ask.y).toBeLessThan(G.Y(16206));
    expect([bid.solid, ask.solid]).toEqual([false, true]);
  });

  it('never lets two chips at one price overlap, nor a chip leave the plot', () => {
    feed([
      drop(T1 - 13.2, { outcome: 'pulled', pulled: 2700, filled: 0, level_before: 6405 }),
      drop(T1 - 11.7, { filled: 1676, level_before: 5082 }),
      drop(T1 - 0.1),
    ]);
    const [pulled, traded, last] = layout(85).chips;
    expect(traded.x).toBeGreaterThanOrEqual(pulled.x + pulled.w + 4);
    expect(last.x + last.w).toBeLessThanOrEqual(1000);
    expect(last.x + last.w).toBeLessThan(G.X(T1 - 0.1));   // past the edge it goes left of its cap
  });
});

describe('the dots\' numbers', () => {
  it('writes the shares inside the big buy and sell dots, never a grey one or a small one', () => {
    feed([]);
    const dots: HeatDot[] = [
      { t: T1 - 15, price: 162.05, shares: 19_093, side: 2 },
      { t: T1 - 5, price: 162.0, shares: 7_885, side: 1 },
      { t: T1 - 20, price: 162.04, shares: 1_200, side: 0 },
    ];
    expect(layout(85, dots, 19_093).numbers.map((n) => n.text)).toEqual(['7.9K']);
    expect([heatDotShares(850), heatDotShares(52_160), heatMarkShares(3719), heatMarkShares(97_127)])
      .toEqual(['850', '52K', '3,719', '97.1K']);
  });
});

describe('hidden size', () => {
  it('boxes the price for as long as the stretch held, cut to the window, its hidden size at the end', () => {
    feed([], [{ id: 'h1', side: 'bid', price: 161.95, state: 'moved', hidden: 97127, printed: 113244,
      shown_max: 16117, started_ts: T1 - 40, ended_ts: T1 - 10, ts: T1 - 10 }]);
    const m = layout(45);
    expect(m.boxes).toHaveLength(1);
    expect(m.boxes[0].x0).toBe(0);
    expect(m.boxes[0].x1).toBeCloseTo(G.X(T1 - 10));
    expect(m.chips.map((c) => c.text)).toEqual(['◆ 97.1K hidden']);
  });
});
