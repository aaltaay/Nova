/**
 * @vitest-environment node
 *
 * The guard is read by src/ibkr transport modules whose own suites declare
 * `@vitest-environment node`. Reading window.location off-browser would throw
 * INSIDE the guard — an order door would blow up rather than refuse — so the
 * off-browser answer is pinned here, in the environment that can observe it
 * (#357). jsdom cannot: it always supplies a window.
 */
import { describe, expect, it } from 'vitest';
import { isSampleView } from './sampleNav';
import { onSampleDesk, sampleKillRefusal, sampleOrderRefusal } from './sampleOrderGuard';

describe('sample guard with no browser', () => {
  it('has no window to read', () => {
    expect(typeof globalThis.window).toBe('undefined');
  });

  it('answers "not the sample desk" instead of throwing', () => {
    expect(() => isSampleView()).not.toThrow();
    expect(isSampleView()).toBe(false);
    expect(onSampleDesk()).toBe(false);
    expect(sampleOrderRefusal()).toBeNull();
    expect(sampleKillRefusal()).toBeNull();
  });

  it('still honours an explicitly passed search string', () => {
    expect(isSampleView('?view=sample')).toBe(true);
    expect(isSampleView('?view=samples')).toBe(false);
  });
});
