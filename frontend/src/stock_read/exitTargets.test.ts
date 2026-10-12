import { describe, expect, it } from 'vitest';
import { splitHalves, targetProblem, usableTarget } from './exitTargets';

describe('the exit sheet splits a position into its halves (#681)', () => {
  it('half at target 1, the rest at target 2; an odd count gives the first half the smaller part', () => {
    expect(splitHalves(100, 7, 7.5, null, false)).toEqual([50, 50]);
    expect(splitHalves(101, 7, 7.5, 0.5, false)).toEqual([50, 51]);
    expect(splitHalves(3, 7, 7.5, null, false)).toEqual([1, 2]);
    expect(splitHalves(100, 7, 7.5, 0.25, false)).toEqual([25, 75]);
  });

  it('one share, no target 2 or a target 2 not beyond target 1 sells every share at target 1', () => {
    expect(splitHalves(1, 7, 7.5, null, false)).toEqual([1, 0]);
    expect(splitHalves(100, 7, null, null, false)).toEqual([100, 0]);
    expect(splitHalves(100, 7, 6.9, null, false)).toEqual([100, 0]);
  });

  it("a short's second target is under its first", () => {
    expect(splitHalves(416, 5.3, 5.0, null, true)).toEqual([208, 208]);
    expect(splitHalves(416, 5.3, 5.4, null, true)).toEqual([416, 0]);
  });
});

describe('what is wrong with a target', () => {
  it('a long: over the price, over the stop, target 2 over target 1', () => {
    expect(targetProblem(false, 6.64, 5.95, null, null)).toBeNull();
    expect(targetProblem(false, 6.64, 5.95, 7, 7.5)).toBeNull();
    expect(targetProblem(false, 6.64, 5.95, 6.5, null)).toMatch(/would sell at once/);
    expect(targetProblem(false, 6.64, 5.95, 7, 6.9)).toMatch(/Target 2 6.90 must be over target 1 7.00/);
    expect(targetProblem(false, 6.64, 5.95, null, 7.5)).toMatch(/needs a target 1/);
  });

  it('a short: under the price and under its buy stop', () => {
    expect(targetProblem(true, 5.46, 5.55, 5.3, 5.0)).toBeNull();
    expect(targetProblem(true, 5.46, 5.55, 5.5, null)).toMatch(/would cover at once/);
  });

  it('a read target already passed is not one to start from', () => {
    expect(usableTarget(false, 5.965, 6.64)).toBeNull();
    expect(usableTarget(false, 7.0, 6.64)).toBe(7.0);
    expect(usableTarget(false, 7.5, 6.64, 7.0)).toBe(7.5);
    expect(usableTarget(true, 5.53, 5.46)).toBeNull();
  });
});
