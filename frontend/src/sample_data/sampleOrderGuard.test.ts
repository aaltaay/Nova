/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { SAMPLE_MARKETING_LABEL } from './sampleCopy';
import { sampleKillRefusal, sampleOrderRefusal } from './sampleOrderGuard';

function at(path: string) {
  window.history.replaceState({}, '', path);
}

describe('sampleOrderRefusal', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('refuses on both sample routes', () => {
    at('/?view=sample');
    expect(sampleOrderRefusal()).toMatch(/Nova Marketing Sample Data/);
    at('/?view=sample&symbol=SMPL');
    expect(sampleOrderRefusal()).toMatch(/Nova Marketing Sample Data/);
  });

  it('never refuses off the sample route', () => {
    // A false positive here would silently block real order placement, so the
    // near-miss URLs are asserted explicitly.
    for (const path of ['/', '/?view=stock&symbol=SMPL', '/?view=samples', '/?view=SAMPLE']) {
      at(path);
      expect(sampleOrderRefusal(), `expected no refusal at ${path}`).toBeNull();
    }
  });

  it('uses marketing wording, never fake / mock / dummy', () => {
    at('/?view=sample');
    const copy = sampleOrderRefusal() ?? '';
    expect(copy).toContain(SAMPLE_MARKETING_LABEL);
    expect(copy).not.toMatch(/fake|mock|dummy/i);
  });
});

describe('sampleKillRefusal', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('refuses on both sample routes with its own actionable copy', () => {
    for (const path of ['/?view=sample', '/?view=sample&symbol=SMPL']) {
      at(path);
      const copy = sampleKillRefusal() ?? '';
      expect(copy, `expected a kill refusal at ${path}`).toContain(SAMPLE_MARKETING_LABEL);
      expect(copy).toMatch(/exit the sample desk/i);
      expect(copy).not.toMatch(/fake|mock|dummy/i);
      // Must not read like an order refusal: the composite also skips the bot
      // PATCH and the desk lock, and the operator has to be told that.
      expect(copy).toMatch(/nothing was cancelled or flattened/i);
    }
  });

  it('leaves Emergency KILL alone on every live route', () => {
    for (const path of ['/', '/?view=stock&symbol=SMPL', '/?view=samples', '/?view=SAMPLE']) {
      at(path);
      expect(sampleKillRefusal(), `expected no kill refusal at ${path}`).toBeNull();
    }
  });
});
