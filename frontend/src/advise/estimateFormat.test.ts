import { describe, expect, it } from 'vitest';
import {
  estimateMatches,
  formatAdviseActualUsd,
  formatAdviseCostHeadline,
  formatAdviseHistoryOption,
} from './estimateFormat';
import { clampAdviseDepth } from './constants';
import { isAdviseSymbol } from './adviseSymbol';
import type { AdviseRun } from './types';

const FAILED: AdviseRun = {
  id: 9,
  symbol: 'SPCX',
  session_date: '2026-09-16',
  created_ts: 1_721_000_000,
  finished_ts: 1_721_000_240,
  model: 'sonnet',
  graph_version: 1,
  depth: 2,
  status: 'failed',
  fail_reason: 'OpenRouter HTTP 402',
  transcript: [],
  result: { stance: null, reasons: [], risks: [], ticket: null },
  disclaimer: 'Advisory only',
  places: false,
  prompt_tokens: 81000,
  completion_tokens: 14000,
  actual_usd: 0.31,
};

describe('advise estimate helpers', () => {
  it('formats the loud cost line as an estimate', () => {
    expect(formatAdviseCostHeadline({ est_usd: 0.19, est_minutes: 4 })).toBe(
      'Estimate: ~$0.19 · ~4 min',
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

  it('formats actual spend at two decimals', () => {
    expect(formatAdviseActualUsd(0.31)).toBe('$0.31');
    expect(formatAdviseActualUsd(null)).toBeNull();
    expect(formatAdviseActualUsd(undefined)).toBeNull();
  });

  it('lists failed runs with actual spend', () => {
    expect(formatAdviseHistoryOption(FAILED)).toMatch(/failed · \$0\.31$/);
  });

  it('omits the dollar when spend is unknown', () => {
    expect(formatAdviseHistoryOption({ ...FAILED, actual_usd: null }))
      .toMatch(/failed$/);
  });
});
