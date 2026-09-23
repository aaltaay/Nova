import { describe, expect, it } from 'vitest';
import { buildCatalystBySymbol, buildNewsBySymbol } from './newsBySymbol';

describe('buildNewsBySymbol', () => {
  it('returns empty map for empty input', () => {
    expect(buildNewsBySymbol([]).size).toBe(0);
  });

  it('uppercases symbols and skips null headlines', () => {
    const map = buildNewsBySymbol([
      { symbol: 'aapl', newest_headline_at: '2026-07-30T12:00:00Z' },
      { symbol: 'MSFT', newest_headline_at: null },
      { symbol: '  tsla  ', newest_headline_at: '2026-07-30T11:00:00Z' },
    ]);
    expect(map.get('AAPL')).toBe('2026-07-30T12:00:00Z');
    expect(map.get('TSLA')).toBe('2026-07-30T11:00:00Z');
    expect(map.has('MSFT')).toBe(false);
  });

  it('keeps the newest timestamp per symbol', () => {
    const map = buildNewsBySymbol([
      { symbol: 'SMTI', newest_headline_at: '2026-07-30T10:00:00Z' },
      { symbol: 'SMTI', newest_headline_at: '2026-07-30T14:00:00Z' },
      { symbol: 'SMTI', newest_headline_at: '2026-07-30T12:00:00Z' },
    ]);
    expect(map.get('SMTI')).toBe('2026-07-30T14:00:00Z');
  });
});

describe('buildCatalystBySymbol', () => {
  const verdict = {
  verdict: 'catalyst', category: 'merger_acquisition', strength: 'weak', title: 'Acme to Acquire Widget Co',
  source: 'prnewswire', published_ts: 1_790_000_000, url: null, negative_too: false, rules_version: 'v5',
} as const;
  it('keeps only rows that carry the field, and a read verdict beats an unread one', () => {
    const map = buildCatalystBySymbol([
      { symbol: 'acme', catalyst: null },
      { symbol: 'ACME', catalyst: verdict },
      { symbol: 'OLD' },
      { symbol: 'NEW', catalyst: null },
    ]);
    expect(map.get('ACME')).toEqual(verdict);
    expect(map.has('OLD')).toBe(false);
    expect(map.has('NEW') && map.get('NEW')).toBe(null);
  });
});
