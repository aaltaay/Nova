import { describe, expect, it } from 'vitest';
import { joinWatchlistOnRow } from './useWatchlistOverlay';
import type { ScannerRow } from '../types/scanner';
import type { WatchlistEntry } from './types';

function row(symbol: string): ScannerRow {
  return {
    symbol,
    price: 1,
    prev_close: 1,
    change_pct: 0,
    change_abs: 0,
    gap_percent: 0,
    volume: 1,
    rel_volume: null,
    has_news: false,
    newest_headline_at: null,
    market_cap: null,
    float: null,
    short_interest: null,
    short_ratio: null,
  };
}

function entry(symbol: string, score = 80): WatchlistEntry {
  return {
    symbol,
    composite_score: score,
    sub_scores: { change_pct: 1, relative_volume: 1, float: 1, catalyst: 1 },
    five_pillars: {
      symbol,
      all_pass: true,
      pass_count: 5,
      total: 5,
      checkmark: '✓',
      pillars: [],
    },
  };
}

describe('joinWatchlistOnRow', () => {
  it('returns the same object when the join did not change', () => {
    const joined = entry('AAA');
    const base = { ...row('AAA'), watchlist: joined, watchlist_score: 80 };
    expect(joinWatchlistOnRow(base, joined)).toBe(base);
  });

  it('clones only when the watchlist join is new', () => {
    const base = row('AAA');
    const next = joinWatchlistOnRow(base, entry('AAA'));
    expect(next).not.toBe(base);
    expect(next.watchlist_score).toBe(80);
    expect(next.symbol).toBe('AAA');
  });
});
