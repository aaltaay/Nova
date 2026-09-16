import { describe, expect, it } from 'vitest';
import { mwcbBannerLabel } from './mwcbDesk';

describe('mwcbBannerLabel', () => {
  it('labels Level 1/2/3 from RSS reason codes', () => {
    expect(mwcbBannerLabel({ level: 1, reason_code: 'MWC1' })).toBe(
      'Market-wide circuit breaker Level 1 (MWC1)',
    );
    expect(mwcbBannerLabel({ level: 2, reason_code: 'MWC2' })).toBe(
      'Market-wide circuit breaker Level 2 (MWC2)',
    );
    expect(mwcbBannerLabel({ level: 3, reason_code: 'MWC3', stale: true })).toBe(
      'Market-wide circuit breaker Level 3 (MWC3) (RSS stale)',
    );
  });

  it('ignores per-symbol LULD codes and missing rows', () => {
    expect(mwcbBannerLabel(null)).toBeNull();
    expect(mwcbBannerLabel({ level: 4, reason_code: 'MWC4' })).toBeNull();
    expect(mwcbBannerLabel({ level: 2, reason_code: 'LUDP' })).toBe(
      'Market-wide circuit breaker Level 2 (LUDP)',
    );
  });
});
