import { describe, expect, it } from 'vitest';
import { marketClockSnapshot } from './marketClock';

describe('marketClockSnapshot', () => {
  it('formats RTH morning in Eastern with seconds', () => {
    // 2026-07-17 10:30:45 ET = 14:30:45 UTC (EDT)
    const snap = marketClockSnapshot(new Date('2026-07-17T14:30:45.000Z'));
    expect(snap.timeLabel).toBe('10:30:45 ET');
    expect(snap.sessionKind).toBe('rth');
    expect(snap.sessionLabel).toBe('RTH');
  });

  it('labels premarket and closed', () => {
    const pre = marketClockSnapshot(new Date('2026-07-17T12:00:00.000Z')); // 08:00 ET
    expect(pre.sessionKind).toBe('premarket');
    const closed = marketClockSnapshot(new Date('2026-07-18T03:00:00.000Z')); // 23:00 ET Fri
    expect(closed.sessionKind).toBe('closed');
  });
});
