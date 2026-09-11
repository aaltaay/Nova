import { describe, expect, it } from 'vitest';
import { prependBounded } from './signalsStreamBound';

describe('prependBounded', () => {
  it('keeps only the newest max items', () => {
    const out = prependBounded(4, [3, 2, 1], 3);
    expect(out).toEqual([4, 3, 2]);
  });

  it('never uses a zero cap', () => {
    expect(prependBounded('a', [], 0)).toEqual(['a']);
  });
});
