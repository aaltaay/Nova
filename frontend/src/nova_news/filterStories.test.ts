import { describe, expect, it } from 'vitest';
import type { NovaNewsStory } from '../types/novaNews';
import { filterStories } from './filterStories';

function story(overrides: Partial<NovaNewsStory> = {}): NovaNewsStory {
  return {
    id: '1',
    headline: 'Test',
    summary: '',
    url: 'https://example.com',
    source: 'Hedgeweek',
    publisher: 'Hedgeweek',
    outlet_kind: 'small',
    criticality: 'watch',
    criticality_score: 40,
    reasons: [],
    symbols: [],
    published_at: null,
    age_hours: null,
    provider: 'hedgeweek',
    tags: ['executes', 'small'],
    ...overrides,
  };
}

describe('filterStories', () => {
  const rows = [
    story({ id: 'a', tags: ['executes', 'funds'] }),
    story({ id: 'b', tags: ['research'], source: 'arXiv' }),
    story({ id: 'c', tags: ['small'], source: 'Hedgeweek' }),
  ];

  it('keeps every story on all', () => {
    expect(filterStories(rows, 'all')).toHaveLength(3);
  });

  it('narrows to executes, funds, research, or small', () => {
    expect(filterStories(rows, 'executes').map((s) => s.id)).toEqual(['a']);
    expect(filterStories(rows, 'funds').map((s) => s.id)).toEqual(['a']);
    expect(filterStories(rows, 'research').map((s) => s.id)).toEqual(['b']);
    expect(filterStories(rows, 'small').map((s) => s.id)).toEqual(['c']);
  });
});
