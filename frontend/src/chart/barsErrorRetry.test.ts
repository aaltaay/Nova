import { describe, expect, it } from 'vitest';
import { shouldScheduleBarsErrorRetry } from './barsErrorRetry';

describe('shouldScheduleBarsErrorRetry', () => {
  it('schedules once for a foreground failure with empty store while active', () => {
    expect(shouldScheduleBarsErrorRetry({
      background: false,
      storeHasBars: false,
      retryAlreadyUsed: false,
      chartActive: true,
    })).toBe(true);
  });

  it('skips background failures, populated store, used retry, or inactive tab', () => {
    expect(shouldScheduleBarsErrorRetry({
      background: true,
      storeHasBars: false,
      retryAlreadyUsed: false,
      chartActive: true,
    })).toBe(false);
    expect(shouldScheduleBarsErrorRetry({
      background: false,
      storeHasBars: true,
      retryAlreadyUsed: false,
      chartActive: true,
    })).toBe(false);
    expect(shouldScheduleBarsErrorRetry({
      background: false,
      storeHasBars: false,
      retryAlreadyUsed: true,
      chartActive: true,
    })).toBe(false);
    expect(shouldScheduleBarsErrorRetry({
      background: false,
      storeHasBars: false,
      retryAlreadyUsed: false,
      chartActive: false,
    })).toBe(false);
  });
});
