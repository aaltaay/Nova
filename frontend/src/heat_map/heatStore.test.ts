/**
 * The heat map's store (ADR 061): books summed per tick with the rows IBKR sent as the seen range, one snapshot per
 * slot, bursts that end on the other side / a pause / a move (never clock slices), volume per second, market time
 * from the prints, and a replay that goes back starts the stock over.
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  heatBursts,
  heatOf,
  heatPendingLine,
  heatVolumeAt,
  noteHeatBeat,
  noteHeatBook,
  noteHeatLine,
  noteHeatPrint,
  resetAllHeatForTests,
  resetHeat,
} from './heatStore';

const T = Date.UTC(2026, 9, 14, 11, 54, 0);   // 07:54:00 ET, as wall ms
const iso = (ms: number) => new Date(ms).toISOString();

afterEach(() => resetAllHeatForTests());

describe('books', () => {
  it('sums the per-exchange rows of one price and keeps the rows IBKR sent as the seen range', () => {
    noteHeatBook('GLND', [{ price: 3.99, size: 400 }, { price: 3.99, size: 650 }, { price: 3.97, size: 100 }],
      [{ price: 4.0, size: 38740 }, { price: 4.02, size: 5507 }], false, T);
    const s = heatOf('GLND')!;
    expect(s.tick).toBe(0.01);
    const sn = s.snaps[0];
    expect(sn.lo).toBe(397);
    expect(sn.sizes.length).toBe(402 - 397 + 1);
    expect(sn.sizes[399 - 397]).toBe(1050);
    expect(sn.sizes[400 - 397]).toBe(38740);
    expect(sn.sizes[398 - 397]).toBe(0);    // inside the rows, nothing waiting
    expect(sn.bb).toBe(399);
    expect(sn.ba).toBe(400);
  });

  it('keeps one book per tenth of a second: the newest in the slot wins', () => {
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, T);
    noteHeatBook('GLND', [{ price: 3.99, size: 200 }], [{ price: 4.0, size: 100 }], false, T + 40);
    noteHeatBook('GLND', [{ price: 3.99, size: 300 }], [{ price: 4.0, size: 100 }], false, T + 150);
    const snaps = heatOf('GLND')!.snaps;
    expect(snaps.length).toBe(2);
    expect(snaps[0].sizes[0]).toBe(200);
    expect(snaps[1].sizes[0]).toBe(300);
  });

  it('bins prices under $1 at a tenth of a cent', () => {
    noteHeatBook('PENY', [{ price: 0.7251, size: 100 }], [{ price: 0.7262, size: 100 }], false, T);
    expect(heatOf('PENY')!.tick).toBe(0.001);
    expect(heatOf('PENY')!.snaps[0].bb).toBe(725);
  });

  it('drops books older than the keep window, keeping the one in force at the cut', () => {
    for (let k = 0; k <= 40; k += 1) {
      noteHeatBook('GLND', [{ price: 3.99, size: k + 1 }], [{ price: 4.0, size: 100 }], false, T + k * 60_000);
    }
    const snaps = heatOf('GLND')!.snaps;
    const cut = snaps[snaps.length - 1].t - 1800;
    expect(snaps[0].t).toBeLessThanOrEqual(cut);
    expect(snaps[1].t).toBeGreaterThanOrEqual(cut);
    expect(snaps.length).toBeLessThan(41);
  });

  it('cuts a far outlier row and takes the best bid / ask from the rows it kept', () => {
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }, { price: 45.0, size: 100 }], [{ price: 4.0, size: 100 }], false, T);
    const sn = heatOf('GLND')!.snaps[0];
    expect(sn.sizes.length).toBeLessThanOrEqual(1001);
    expect(sn.bb).toBe(399);                  // not the cut-off $45 row
    expect(sn.ba).toBe(400);
  });

  it('cuts the far-off row of a two-row book, around where the stock trades', () => {
    noteHeatBook('SPRS', [{ price: 3.99, size: 100 }, { price: 45.0, size: 100 }], [], false, T);   // no reference yet
    expect(heatOf('SPRS')!.snaps[0].bb).toBe(399);
    // The lower middle row of [0.10, 39.99] is the bad $0.10: only where the stock trades can pick $39.99.
    noteHeatPrint('THIN', iso(T), 39.99, 100, 'bid', T);
    noteHeatBook('THIN', [{ price: 39.99, size: 100 }, { price: 0.1, size: 100 }], [], false, T + 100);
    expect(heatOf('THIN')!.snaps[0].bb).toBe(3999);                                              // the last print decides
    noteHeatBook('MID', [{ price: 39.99, size: 100 }], [{ price: 40.0, size: 100 }], false, T);
    noteHeatBook('MID', [{ price: 0.1, size: 100 }, { price: 39.99, size: 100 }], [], false, T + 500);
    expect(heatOf('MID')!.snaps[1].bb).toBe(3999);                                               // else the last middle
  });

  it('keeps why a line was refused or lent before the stock had any book or print', () => {
    noteHeatLine('NEWS', 'error', 'Max number of market depth requests reached');
    expect(heatOf('NEWS')).toBeNull();
    expect(heatPendingLine('NEWS')).toEqual({ state: 'error', why: 'Max number of market depth requests reached' });
    noteHeatBook('NEWS', [{ price: 2.5, size: 100 }], [{ price: 2.51, size: 100 }], false, T);
    expect(heatPendingLine('NEWS')).toBeNull();
  });

  it('notes beats and a lent or refused line', () => {
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, T);
    noteHeatBeat('GLND', T + 5000);
    expect(heatOf('GLND')!.aliveT).toBeCloseTo(T / 1000 + 5, 3);
    noteHeatLine('GLND', 'error', 'IBKR refused depth');
    expect(heatOf('GLND')!.line).toEqual({ state: 'error', why: 'IBKR refused depth' });
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, T + 6000);
    expect(heatOf('GLND')!.line).toBeNull();
  });
});

describe('prints as bursts', () => {
  it('a burst of buying lasts until a seller steps in', () => {
    noteHeatPrint('GLND', iso(T), 4.0, 1000, 'ask', T);
    noteHeatPrint('GLND', iso(T + 200), 4.0, 2000, 'ask', T + 200);
    noteHeatPrint('GLND', iso(T + 300), 3.99, 500, 'bid', T + 300);
    noteHeatPrint('GLND', iso(T + 400), 4.0, 700, 'ask', T + 400);
    const b = heatBursts(heatOf('GLND')!);
    expect(b.map((x) => [x.side, x.sz])).toEqual([[0, 3000], [1, 500], [0, 700]]);
  });

  it('ends a burst after a pause or a move of more than two ticks, and keeps in-between prints apart', () => {
    noteHeatPrint('GLND', iso(T), 4.0, 100, 'ask', T);
    noteHeatPrint('GLND', iso(T + 1500), 4.0, 100, 'ask', T + 1500);           // a pause over a second
    noteHeatPrint('GLND', iso(T + 1600), 4.03, 100, 'ask', T + 1600);          // three ticks from 4.00
    noteHeatPrint('GLND', iso(T + 1700), 4.015, 300, 'between', T + 1700);     // its own stream
    noteHeatPrint('GLND', iso(T + 1800), 4.03, 100, 'ask', T + 1800);          // does not break the buying
    const b = heatBursts(heatOf('GLND')!);
    expect(b.filter((x) => x.side === 0).map((x) => x.sz)).toEqual([100, 100, 200]);
    expect(b.filter((x) => x.side === 2).map((x) => x.sz)).toEqual([300]);
  });

  it('groups in-between prints into their own bursts by the same pause and move rules (never into buying or selling)', () => {
    noteHeatPrint('GLND', iso(T), 3.995, 300, 'between', T);
    noteHeatPrint('GLND', iso(T + 200), 3.995, 400, 'unknown', T + 200);   // one burst of in-between prints
    noteHeatPrint('GLND', iso(T + 300), 4.0, 100, 'ask', T + 300);         // buying does not join it
    noteHeatPrint('GLND', iso(T + 2000), 3.995, 500, 'between', T + 2000); // after a pause: a new burst
    const b = heatBursts(heatOf('GLND')!);
    expect(b.filter((x) => x.side === 2).map((x) => x.sz)).toEqual([700, 500]);
    expect(b.filter((x) => x.side === 0).map((x) => x.sz)).toEqual([100]);
  });

  it('counts volume per second on each side', () => {
    noteHeatPrint('GLND', iso(T), 4.0, 1000, 'ask', T);
    noteHeatPrint('GLND', iso(T + 300), 3.99, 400, 'bid', T + 300);
    noteHeatPrint('GLND', iso(T + 600), 3.995, 50, 'unknown', T + 600);
    expect(heatVolumeAt(heatOf('GLND')!, Math.floor(T / 1000))).toEqual([1000, 400, 50]);
  });

  it('takes market time from the prints: books follow a replay clock', () => {
    const replay = Date.UTC(2026, 9, 14, 11, 54, 0);
    const wall = Date.UTC(2026, 9, 21, 1, 30, 0);
    noteHeatPrint('GLND', iso(replay), 4.0, 100, 'ask', wall);
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, wall + 1000);
    expect(heatOf('GLND')!.snaps[0].t).toBeCloseTo(replay / 1000 + 1, 3);
  });

  it('moves books that came before the first print onto the replay clock, keeping them in order', () => {
    const replay = Date.UTC(2026, 9, 14, 11, 54, 0);
    const wall = Date.UTC(2026, 9, 21, 1, 30, 0);
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, wall);
    noteHeatBeat('GLND', wall + 500);
    noteHeatPrint('GLND', iso(replay + 1000), 4.0, 100, 'ask', wall + 1000);
    noteHeatBook('GLND', [{ price: 3.99, size: 200 }], [{ price: 4.0, size: 100 }], false, wall + 2000);
    const s = heatOf('GLND')!;
    expect(s.snaps.map((x) => x.t)).toEqual([replay / 1000, replay / 1000 + 2]);
    expect(s.aliveT).toBeCloseTo(replay / 1000 + 2, 3);
  });

  it('on a replay clock, beats (browser time) never stretch the last book; prints move it on', () => {
    const replay = Date.UTC(2026, 9, 14, 11, 54, 0);
    const wall = Date.UTC(2026, 9, 21, 1, 30, 0);
    noteHeatPrint('GLND', iso(replay), 4.0, 100, 'ask', wall);
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, wall + 100);
    const before = heatOf('GLND')!.aliveT;
    noteHeatBeat('GLND', wall + 60_000);        // a paused replay: beats keep coming on the browser clock
    expect(heatOf('GLND')!.aliveT).toBe(before);
    noteHeatPrint('GLND', iso(replay + 3000), 4.0, 100, 'ask', wall + 3000);
    expect(heatOf('GLND')!.aliveT).toBeCloseTo(replay / 1000 + 3, 3);
  });

  it('puts books that came between a pause and the next print back on the replay clock, in order', () => {
    const replay = Date.UTC(2026, 9, 14, 11, 54, 0);
    const wall = Date.UTC(2026, 9, 21, 1, 30, 0);
    noteHeatPrint('GLND', iso(replay), 4.0, 100, 'ask', wall);
    noteHeatBook('GLND', [{ price: 3.99, size: 100 }], [{ price: 4.0, size: 100 }], false, wall + 500);
    // paused for 60 s; on resume a book arrives before the replay's next print
    noteHeatBook('GLND', [{ price: 3.99, size: 200 }], [{ price: 4.0, size: 100 }], false, wall + 61_000);
    noteHeatPrint('GLND', iso(replay + 1000), 4.0, 100, 'ask', wall + 61_200);
    const ts = heatOf('GLND')!.snaps.map((x) => x.t - replay / 1000);
    expect(ts[0]).toBeCloseTo(0.5, 3);
    expect(ts[1]).toBeGreaterThanOrEqual(ts[0]);
    expect(ts[1]).toBeLessThan(2);
  });

  it('a replay that goes back starts the stock over, as a scrub does', () => {
    noteHeatPrint('GLND', iso(T + 60_000), 4.0, 100, 'ask', T);
    noteHeatPrint('GLND', iso(T), 3.9, 100, 'bid', T + 100);
    const s = heatOf('GLND')!;
    expect(heatBursts(s).map((b) => b.sz)).toEqual([100]);
    expect(s.lastPrice).toBe(3.9);
    resetHeat('GLND');
    expect(heatOf('GLND')!.bursts.length).toBe(0);
  });

  it('ignores prints with no size or price', () => {
    noteHeatPrint('GLND', iso(T), 4.0, 0, 'ask', T);
    noteHeatPrint('GLND', iso(T), Number.NaN, 100, 'ask', T);
    expect(heatOf('GLND')).toBeNull();
  });
});
