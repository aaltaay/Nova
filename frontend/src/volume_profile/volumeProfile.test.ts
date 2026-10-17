import { describe, expect, it } from 'vitest';
import { buildProfile, type ProfileBar } from './volumeProfile';

const flat = (t: number, price: number, v: number): ProfileBar => ({ t, o: price, h: price, l: price, c: price, v });

describe('buildProfile', () => {
  it('is null when nothing traded in the range', () => {
    expect(buildProfile([], 0, 100)).toBeNull();
    expect(buildProfile([flat(500, 10, 100)], 0, 100)).toBeNull();
  });

  it('finds the POC and grows the value area toward the heavier side', () => {
    // One bar spread over 100-101 puts 1 share in each of 10 rows; flat bars stack the rest.
    const bars: ProfileBar[] = [
      { t: 0, o: 100, h: 101, l: 100, c: 101, v: 10 },
      flat(60, 100.45, 50),
      flat(120, 100.55, 30),
      flat(180, 100.35, 20),
      flat(240, 100.75, 5),
    ];
    const p = buildProfile(bars, 0, 300, 10)!;
    expect(p.rowSize).toBeCloseTo(0.1);
    const rows = p.up.map((u, i) => Math.round(u + p.down[i]));
    expect(rows).toEqual([1, 1, 1, 21, 51, 31, 1, 6, 1, 1]);
    expect(p.pocRow).toBe(4);
    expect(p.poc).toBeCloseTo(100.45);
    // 51 held; the two rows above (32) beat the two below (22), and 83 of 115 is past 70%.
    expect([p.valRow, p.vahRow]).toEqual([4, 6]);
    expect(p.val).toBeCloseTo(100.4);
    expect(p.vah).toBeCloseTo(100.7);
  });

  it('only measures bars that start inside [from, to)', () => {
    const p = buildProfile([flat(0, 50, 999), flat(60, 10, 100), flat(120, 11, 300)], 60, 180, 10)!;
    expect(p.total).toBeCloseTo(400);
    expect(p.low).toBe(10);
    expect(p.high).toBe(11);
  });

  it('gives a tie for the POC to the row nearest the middle', () => {
    const bars = [flat(0, 10.05, 5), flat(60, 10.45, 5), flat(120, 10.95, 5), { t: 180, o: 10, h: 11, l: 10, c: 10, v: 0.0001 }];
    const p = buildProfile(bars, 0, 300, 10)!;
    expect(p.pocRow).toBe(4);
  });

  it('splits each row into volume on up and down bars', () => {
    const p = buildProfile([
      { t: 0, o: 10, h: 10, l: 10, c: 10, v: 70 },
      { t: 60, o: 10.2, h: 10.2, l: 10, c: 10, v: 30 },
    ], 0, 120, 2)!;
    expect(p.up[0]).toBeCloseTo(70 + 0);
    expect(p.down[0] + p.down[1]).toBeCloseTo(30);
  });
});
