import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  isStuckLoadingBars,
  nextStuckRetryDelayMs,
  startStuckBarsRetries,
} from './chartBarsStuckRetry';

afterEach(() => {
  vi.useRealTimers();
});

describe('isStuckLoadingBars', () => {
  it('is stuck when the pane is active, still filling, and has no bars yet', () => {
    expect(isStuckLoadingBars({ filling: true, hasBars: false, chartActive: true })).toBe(true);
  });

  it('is not stuck once bars arrive', () => {
    expect(isStuckLoadingBars({ filling: true, hasBars: true, chartActive: true })).toBe(false);
  });

  it('is not stuck once filling ends (real error path takes over instead)', () => {
    expect(isStuckLoadingBars({ filling: false, hasBars: false, chartActive: true })).toBe(false);
  });

  it('is not stuck while the pane is inactive', () => {
    expect(isStuckLoadingBars({ filling: true, hasBars: false, chartActive: false })).toBe(false);
  });
});

describe('nextStuckRetryDelayMs', () => {
  it('doubles the previous delay', () => {
    expect(nextStuckRetryDelayMs(3000, 3000, 15000)).toBe(6000);
    expect(nextStuckRetryDelayMs(6000, 3000, 15000)).toBe(12000);
  });

  it('caps at maxMs so it keeps retrying forever, never stopping', () => {
    expect(nextStuckRetryDelayMs(12000, 3000, 15000)).toBe(15000);
    expect(nextStuckRetryDelayMs(15000, 3000, 15000)).toBe(15000);
  });

  it('never goes below minMs', () => {
    expect(nextStuckRetryDelayMs(0, 3000, 15000)).toBe(3000);
  });
});

describe('startStuckBarsRetries', () => {
  it('keeps retrying when an empty filling response does not trigger a React render', async () => {
    vi.useFakeTimers();
    const retry = vi.fn().mockResolvedValue(undefined);

    const stop = startStuckBarsRetries(retry, 3000, 15000);
    await vi.advanceTimersByTimeAsync(3000);
    expect(retry).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(6000);
    expect(retry).toHaveBeenCalledTimes(2);

    stop();
    await vi.advanceTimersByTimeAsync(15000);
    expect(retry).toHaveBeenCalledTimes(2);
  });
});
