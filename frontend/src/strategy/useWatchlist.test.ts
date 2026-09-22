import { describe, expect, it } from 'vitest';
import { readWatchlistEntries } from './useWatchlist';

const entry = (symbol: string) => ({
  symbol,
  composite_score: 72,
  sub_scores: { change_pct: 1, relative_volume: 1, float: 1, catalyst: 1 },
  five_pillars: { symbol, all_pass: false, pass_count: 3, total: 5, checkmark: '·', pillars: [] },
});

describe('readWatchlistEntries (QA C15)', () => {
  it('refuses a JSON array: data.entries is Array.prototype.entries, a function', () => {
    expect(typeof ([] as unknown as { entries: unknown }).entries).toBe('function');
    expect(readWatchlistEntries([])).toBeNull();
    expect(readWatchlistEntries([entry('GRML')])).toBeNull();
  });

  it('refuses bodies that carry no entry list', () => {
    expect(readWatchlistEntries(null)).toBeNull();
    expect(readWatchlistEntries('ok')).toBeNull();
    expect(readWatchlistEntries({ entries: 'GRML' })).toBeNull();
    expect(readWatchlistEntries({ note: 'x', count: 0 })).toBeNull();
  });

  it('keeps well-formed entries and drops ones a renderer would crash on', () => {
    const out = readWatchlistEntries({
      note: 'x',
      count: 4,
      entries: [entry('GRML'), { symbol: 'NOPILLARS', composite_score: 50 }, { composite_score: 1 }, entry('VXTL')],
    });
    expect(out?.map((e) => e.symbol)).toEqual(['GRML', 'VXTL']);
    expect(readWatchlistEntries({ entries: [] })).toEqual([]);
  });
});
