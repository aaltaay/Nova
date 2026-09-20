/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { SAMPLE_MARKETING_LABEL } from './sampleCopy';
import { sampleOrderRefusal } from './sampleOrderGuard';

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
