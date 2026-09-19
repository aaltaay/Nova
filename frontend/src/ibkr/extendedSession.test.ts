import { describe, expect, it } from 'vitest';
import {
  etMinutesNow,
  flattenNeedsOutsideRth,
  isExtendedTradingSessionNow,
  isWeekdayRegularHoursNow,
  resolveFillSessionKind,
  sessionKindNow,
} from './extendedSession';

describe('extendedSession', () => {
  it('classifies premarket as extended', () => {
    // 2026-07-18 08:00 ET = 12:00 UTC (EDT)
    const d = new Date('2026-07-18T12:00:00.000Z');
    expect(etMinutesNow(d)).toBe(8 * 60);
    expect(sessionKindNow(d)).toBe('premarket');
    expect(isExtendedTradingSessionNow(d)).toBe(true);
  });

  it('classifies RTH as not extended', () => {
    // 2026-07-18 10:30 ET = 14:30 UTC
    const d = new Date('2026-07-18T14:30:00.000Z');
    expect(isExtendedTradingSessionNow(d)).toBe(false);
  });

  it('classifies after-hours as extended', () => {
    // 2026-07-18 17:00 ET = 21:00 UTC
    const d = new Date('2026-07-18T21:00:00.000Z');
    expect(isExtendedTradingSessionNow(d)).toBe(true);
  });

  it('treats Saturday clock-RTH as outside RTH for flatten', () => {
    // 2026-09-19 10:30 ET = 14:30 UTC -- Saturday
    const d = new Date('2026-09-19T14:30:00.000Z');
    expect(sessionKindNow(d)).toBe('rth');
    expect(isWeekdayRegularHoursNow(d)).toBe(false);
    expect(flattenNeedsOutsideRth(d)).toBe(true);
    expect(resolveFillSessionKind({ now: d })).toBe('closed');
  });

  it('keeps Friday 10:30 ET as weekday RTH', () => {
    const d = new Date('2026-09-18T14:30:00.000Z');
    expect(isWeekdayRegularHoursNow(d)).toBe(true);
    expect(flattenNeedsOutsideRth(d)).toBe(false);
    expect(resolveFillSessionKind({ now: d })).toBe('rth');
  });
});
