import { describe, expect, it } from 'vitest';
import { isCurrentBarsRequest } from './requestVersion';

describe('isCurrentBarsRequest', () => {
  it('accepts matching versions', () => {
    expect(isCurrentBarsRequest(3, 3)).toBe(true);
  });

  it('rejects stale responses after symbol/timeframe bump', () => {
    expect(isCurrentBarsRequest(2, 3)).toBe(false);
  });
});
