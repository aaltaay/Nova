import { describe, expect, it } from 'vitest';
import type { NovaNewsStory } from '../types/novaNews';
import { filterStories } from './filterStories';

function story(overrides: Partial<NovaNewsStory> = {}): NovaNewsStory {
  return {
    id: '1',
    headline: 'Test',
    summary: '',
    url: 'https://example.com',
    source: 'Yahoo Finance',
    publisher: 'Yahoo Finance',
    outlet_kind: 'yahoo',
    criticality: 'watch',
    criticality_score: 40,
    reasons: [],
    symbols: [],
    published_at: null,
    age_hours: null,
    provider: 'yahoo_finance',
    tags: ['yahoo', 'markets'],
    ...overrides,
  };
}

describe('filterStories', () => {
  const rows = [
    story({ id: 'a', tags: ['yahoo', 'markets'] }),
    story({ id: 'b', tags: ['filings'], source: 'SEC' }),
    story({ id: 'c', tags: ['small', 'markets'], source: 'Hedgeweek' }),
  ];

  it('keeps every story on all', () => {
    expect(filterStories(rows, 'all')).toHaveLength(3);
  });

  it('narrows to yahoo or small without dropping unknown tags', () => {
    expect(filterStories(rows, 'yahoo').map((s) => s.id)).toEqual(['a']);
    expect(filterStories(rows, 'small').map((s) => s.id)).toEqual(['c']);
    expect(filterStories(rows, 'filings').map((s) => s.id)).toEqual(['b']);
  });
});
