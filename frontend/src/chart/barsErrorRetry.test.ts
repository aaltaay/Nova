import { describe, expect, it } from 'vitest';
import { shouldScheduleBarsErrorRetry } from './barsErrorRetry';

describe('shouldScheduleBarsErrorRetry', () => {
  it('schedules while the store is empty, the tab is active, and retries remain', () => {
    expect(shouldScheduleBarsErrorRetry({
      storeHasBars: false,
      retriesUsed: 0,
      maxRetries: 8,
      chartActive: true,
    })).toBe(true);
    expect(shouldScheduleBarsErrorRetry({
      storeHasBars: false,
      retriesUsed: 7,
      maxRetries: 8,
      chartActive: true,
    })).toBe(true);
  });

  it('stops when the store has bars, retries are exhausted, or the tab is hidden', () => {
    expect(shouldScheduleBarsErrorRetry({
      storeHasBars: true,
      retriesUsed: 0,
      maxRetries: 8,
      chartActive: true,
    })).toBe(false);
    expect(shouldScheduleBarsErrorRetry({
      storeHasBars: false,
      retriesUsed: 8,
      maxRetries: 8,
      chartActive: true,
    })).toBe(false);
    expect(shouldScheduleBarsErrorRetry({
      storeHasBars: false,
      retriesUsed: 0,
      maxRetries: 8,
      chartActive: false,
    })).toBe(false);
  });
});
