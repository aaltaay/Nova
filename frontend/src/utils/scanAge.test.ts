import { describe, expect, it } from 'vitest';
import { scanAgeForTab } from './scanAge';

describe('scanAgeForTab', () => {
  const ages = { gappers: 100, movers: 200, afterhours: 10 };

  it('uses the active scanner tab timestamp', () => {
    expect(scanAgeForTab('gappers', ages)).toBe(100);
    expect(scanAgeForTab('movers', ages)).toBe(200);
    expect(scanAgeForTab('afterhours', ages)).toBe(10);
  });

  it('falls back to the freshest age for non-scanner tabs', () => {
    expect(scanAgeForTab('watchlist', ages)).toBe(200);
    expect(scanAgeForTab('trading', ages)).toBe(200);
  });
});
