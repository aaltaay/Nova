import { describe, expect, it } from 'vitest';
import { parseReviewQuery, reviewHref } from './reviewQuery';

describe('review query', () => {
  it('reads one symbol, a date and the desk pane order', () => {
    const query = parseReviewQuery('?symbol=imcc&date=2026-09-18&tf=1m,5m,1d');
    expect(query.gallery).toBe(false);
    expect(query.symbols).toEqual(['IMCC']);
    expect(query.date).toBe('2026-09-18');
    expect(query.tfs).toEqual(['5m', '1d', '1m']);
    expect(query.asOf).toBe('16:00');
    expect(query.fixture).toBe(false);
  });

  it('treats a symbols list as a gallery and keeps fixture links', () => {
    const query = parseReviewQuery('?symbols=a,b,c&date=2026-09-18&fixture=1');
    expect(query.gallery).toBe(true);
    expect(query.symbols).toEqual(['A', 'B', 'C']);
    expect(query.tfs).toEqual(['5m', '10s', '1d', '1m']);
    expect(reviewHref('A', '2026-09-18', query.tfs, '16:00', true)).toBe(
      '/review?symbol=A&date=2026-09-18&tf=5m%2C10s%2C1d%2C1m&fixture=1',
    );
  });
});
