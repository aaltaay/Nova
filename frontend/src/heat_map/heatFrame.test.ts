/**
 * One heat map frame as numbers (ADR 061): the padded price range, the book averaged by time into columns (a slice
 * counts as seen only when IBKR's rows covered it at least half the time; never drawn as an empty book), the middle
 * of the bid and ask, dots over the size filter, and volume bars.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { heatBookAt, heatDots, heatGrid, heatMid, heatNow, heatRange, heatVolume } from './heatFrame';
import { heatOf, noteHeatBeat, noteHeatBook, noteHeatPrint, resetAllHeatForTests } from './heatStore';

const T = Date.UTC(2026, 9, 14, 11, 54, 0);
const t0 = T / 1000;
const iso = (ms: number) => new Date(ms).toISOString();

afterEach(() => resetAllHeatForTests());

function book(atMs: number, ask400: number) {
  noteHeatBook('GLND', [{ price: 3.99, size: 1000 }, { price: 3.98, size: 500 }],
    [{ price: 4.0, size: ask400 }, { price: 4.01, size: 200 }], false, atMs);
}

describe('heatRange', () => {
  it('pads the best bid / ask extremes and keeps at least the minimum span', () => {
    book(T, 100);
    noteHeatBeat('GLND', T + 10_000);
    const r = heatRange(heatOf('GLND')!, { t0, t1: t0 + 10 })!;
    expect(r.lo).toBeLessThanOrEqual(399 - 3);
    expect(r.hi).toBeGreaterThanOrEqual(400 + 3);
    expect(r.hi - r.lo).toBeGreaterThanOrEqual(20);
  });

  it('is null with no book in the window', () => {
    noteHeatPrint('GLND', iso(T), 4.0, 100, 'ask', T);
    expect(heatRange(heatOf('GLND')!, { t0, t1: t0 + 10 })).toBeNull();
  });
});

describe('heatGrid', () => {
  it('averages the books in force during each column by time', () => {
    book(T, 1000);
    book(T + 5000, 3000);
    noteHeatBeat('GLND', T + 10_000);
    const s = heatOf('GLND')!;
    const range = { lo: 398, hi: 401 };
    const g = heatGrid(s, { t0, t1: t0 + 10 }, range, 2);
    const at = (tick: number, col: number) => g.size[(tick - range.lo) * g.cols + col];
    expect(at(400, 0)).toBeCloseTo(1000, 0);
    expect(at(400, 1)).toBeCloseTo(3000, 0);
    const one = heatGrid(s, { t0, t1: t0 + 10 }, range, 1);
    expect(one.size[(400 - range.lo) * one.cols]).toBeCloseTo(2000, 0);
  });

  it('marks a price outside the rows IBKR sent as not seen, never as an empty level', () => {
    book(T, 1000);
    noteHeatBeat('GLND', T + 10_000);
    const range = { lo: 395, hi: 405 };
    const g = heatGrid(heatOf('GLND')!, { t0, t1: t0 + 10 }, range, 4);
    expect(g.seen[(396 - range.lo) * g.cols]).toBe(0);    // below the deepest bid row
    expect(g.seen[(398 - range.lo) * g.cols]).toBe(1);
    expect(g.seen[(404 - range.lo) * g.cols]).toBe(0);    // above the deepest ask row
  });

  it('goes black once the line stops beating (the last book is not drawn forever)', () => {
    book(T, 1000);
    noteHeatBeat('GLND', T + 8000);    // alive to 8 s, plus the grace: the first 10 s column is covered
    const range = { lo: 398, hi: 401 };
    const g = heatGrid(heatOf('GLND')!, { t0, t1: t0 + 60 }, range, 6);
    expect(g.seen[(400 - range.lo) * g.cols]).toBe(1);
    expect(g.seen[(400 - range.lo) * g.cols + 5]).toBe(0);
    expect(heatBookAt(heatOf('GLND')!, t0 + 59)).toBeNull();
  });
});

describe('heatMid, heatDots, heatVolume, heatNow', () => {
  it('draws the middle of the bid and ask where a book is in force', () => {
    book(T, 1000);
    noteHeatBeat('GLND', T + 10_000);
    const m = heatMid(heatOf('GLND')!, { t0, t1: t0 + 10 }, 5);
    expect(m[0]).toBeCloseTo(399.5, 5);
  });

  it('keeps only bursts over the size filter, biggest first', () => {
    noteHeatPrint('GLND', iso(T), 4.0, 3000, 'ask', T);
    noteHeatPrint('GLND', iso(T + 100), 3.99, 400, 'bid', T + 100);
    noteHeatPrint('GLND', iso(T + 200), 4.0, 9000, 'ask', T + 200);
    const dots = heatDots(heatOf('GLND')!, { t0: t0 - 1, t1: t0 + 5 }, 1000);
    expect(dots.map((d) => d.shares)).toEqual([9000, 3000]);
    expect(dots[0].price).toBeCloseTo(4.0, 6);
  });

  it('sums volume into the window bars', () => {
    noteHeatPrint('GLND', iso(T + 500), 4.0, 1000, 'ask', T + 500);
    noteHeatPrint('GLND', iso(T + 7500), 3.99, 200, 'bid', T + 7500);
    const v = heatVolume(heatOf('GLND')!, { t0, t1: t0 + 10 }, 2);
    expect(v).toEqual([[1000, 0, 0], [0, 200, 0]]);
  });

  it('holds the right edge at the newest data while a replay is paused', () => {
    noteHeatPrint('GLND', iso(T), 4.0, 100, 'ask', T);
    expect(heatNow(heatOf('GLND')!, T + 60_000)).toBeCloseTo(t0 + 5, 3);
  });
});
