import { describe, expect, it } from 'vitest';
import { nextHodMomoRenderedCount } from './HodMomoAlertTable';

describe('nextHodMomoRenderedCount', () => {
  it('adds exactly one forty-row batch', () => {
    expect(nextHodMomoRenderedCount(40, 8_000)).toBe(80);
  });

  it('stops at the available alert count', () => {
    expect(nextHodMomoRenderedCount(80, 93)).toBe(93);
  });
});
