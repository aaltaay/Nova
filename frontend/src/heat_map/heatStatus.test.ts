/** What the heat map says when it has no lines to draw (ADR 061): never a silent black screen, never a false alarm. */
import { afterEach, describe, expect, it } from 'vitest';
import { heatRange } from './heatFrame';
import { heatStatus } from './heatStatus';
import { heatOf, noteHeatBeat, noteHeatBook, noteHeatLine, noteHeatPrint, resetAllHeatForTests } from './heatStore';

const T = Date.UTC(2026, 9, 14, 11, 54, 0);
const iso = (ms: number) => new Date(ms).toISOString();

afterEach(() => resetAllHeatForTests());

describe('heatStatus', () => {
  it("says IBKR's reason when the line was refused before any book arrived", () => {
    noteHeatLine('NEWS', 'error', 'Max number of market depth requests reached');
    expect(heatStatus(heatOf('NEWS'), 'NEWS', T)).toContain('Max number of market depth requests reached');
  });

  it('waits for the first book, then says nothing while the line beats, then says when it went quiet', () => {
    expect(heatStatus(null, 'GLND', T)).toContain("Waiting for GLND's Level 2");
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, T);
    noteHeatBeat('GLND', T + 5000);
    expect(heatStatus(heatOf('GLND'), 'GLND', T + 6000)).toBeNull();
    expect(heatStatus(heatOf('GLND'), 'GLND', T + 60_000)).toContain('No Level 2 since');
  });

  it('a paused replay is not a quiet line', () => {
    const wall = Date.UTC(2026, 9, 21, 1, 30, 0);
    noteHeatPrint('GLND', iso(T), 4.0, 100, 'ask', wall);
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, wall + 100);
    expect(heatStatus(heatOf('GLND'), 'GLND', wall + 600_000)).toBeNull();
  });
});

describe('heatRange caps the screen', () => {
  it('never spans more than the most ticks a screen shows', () => {
    for (let k = 0; k < 30; k += 1) {
      const p = 100 + k;                            // a $30 move inside the window
      noteHeatBook('BIG', [{ price: p - 0.01, size: 100 }], [{ price: p, size: 100 }], false, T + k * 1000);
    }
    noteHeatBeat('BIG', T + 31_000);
    const r = heatRange(heatOf('BIG')!, { t0: T / 1000, t1: T / 1000 + 31 })!;
    expect(r.hi - r.lo).toBeLessThanOrEqual(1200 + 2 * 3);
    expect(r.hi).toBeGreaterThanOrEqual(12900);    // around the newest middle ($129)
  });
});
