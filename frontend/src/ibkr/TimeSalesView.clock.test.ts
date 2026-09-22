import { describe, expect, it } from 'vitest';
import { fmtTapeTime } from './TimeSalesView';

describe('the tape clock is Eastern whatever the browser zone (QA W24)', () => {
  it('prints HH:MM:SS in ET', () => {
    // 09:44:02 UTC on Sep 22 is 05:44:02 EDT.
    expect(fmtTapeTime('2026-09-22T09:44:02Z')).toBe('05:44:02');
    // 04:00:00 UTC is midnight ET: 00, never 24.
    expect(fmtTapeTime('2026-09-22T04:00:00Z')).toBe('00:00:00');
  });
});
