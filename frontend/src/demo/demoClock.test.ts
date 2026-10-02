/**
 * The demo's clock (ADR 043): `Date` starts at the sample morning and runs; everything else a Date
 * does is untouched.
 */
import { describe, expect, it } from 'vitest';
import { installDemoClock } from './demoClock';

const START = Date.UTC(2026, 8, 30, 13, 41, 27); // 09:41:27 ET

describe('installDemoClock', () => {
  it('starts at the sample morning and keeps every other Date behaviour', () => {
    const win = { Date };
    const restore = installDemoClock(START, win);
    const D = win.Date;
    expect(Math.abs(D.now() - START)).toBeLessThan(1000);
    expect(Math.abs(new D().getTime() - START)).toBeLessThan(1000);
    expect(new D(0).getTime()).toBe(0);
    expect(new D(2026, 0, 2).getFullYear()).toBe(2026);
    expect(new D() instanceof Date).toBe(true);
    expect(D.UTC(2026, 0, 1)).toBe(Date.UTC(2026, 0, 1));
    expect(D.parse('2026-09-30T13:41:27Z')).toBe(START);
    expect(typeof (D as unknown as () => string)()).toBe('string');
    restore();
    expect(win.Date).toBe(Date);
  });
});
