import { describe, expect, it } from 'vitest';
import { estimateMatches, formatAdviseCostHeadline } from './estimateFormat';
import { clampAdviseDepth } from './constants';
import { isAdviseSymbol } from './adviseSymbol';

describe('advise estimate helpers', () => {
  it('formats the loud cost line', () => {
    expect(formatAdviseCostHeadline({ est_usd: 0.19, est_minutes: 4 })).toBe(
      '~$0.19 · ~4 min',
    );
  });

  it('matches only the current symbol and depth', () => {
    const estimate = {
      symbol: 'AAPL',
      depth: 2,
      model: 'sonnet',
      model_label: 'Sonnet',
      llm_calls: 14,
      est_usd: 0.19,
      est_minutes: 4,
      summary: 'sum',
      disclaimer: 'd',
      note: 'n',
    };
    expect(estimateMatches(estimate, 'AAPL', 2)).toBe(true);
    expect(estimateMatches(estimate, 'MSFT', 2)).toBe(false);
    expect(estimateMatches(estimate, 'AAPL', 5)).toBe(false);
  });

  it('clamps depth and rejects junk tickers', () => {
    expect(clampAdviseDepth(0)).toBe(1);
    expect(clampAdviseDepth(99)).toBe(5);
    expect(isAdviseSymbol('AAPL')).toBe(true);
    expect(isAdviseSymbol('???')).toBe(false);
    expect(isAdviseSymbol('')).toBe(false);
  });
});
