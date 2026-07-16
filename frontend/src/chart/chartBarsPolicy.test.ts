import { describe, expect, it } from 'vitest';
import { allowMockBarsFallback, emptyBarsMessage } from './chartBarsPolicy';

describe('chartBarsPolicy', () => {
  it('forbids mock bars when discovery is ibkr', () => {
    expect(allowMockBarsFallback('ibkr')).toBe(false);
    expect(emptyBarsMessage('ibkr')).toMatch(/IBKR/);
  });

  it('allows mock bars when discovery is alpaca', () => {
    expect(allowMockBarsFallback('alpaca')).toBe(true);
    expect(emptyBarsMessage('alpaca')).toMatch(/No chart bars/);
  });
});
