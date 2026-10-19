import { describe, expect, it } from 'vitest';
import { sessionVisibleRange } from './reviewFit';
import { galleryFrame, parseReviewQuery, reviewHref } from './reviewQuery';

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

  it('keeps a loopback review API and picks one gallery frame', () => {
    const query = parseReviewQuery('?symbol=A&date=2026-09-18&tf=1m,1d&api=http://127.0.0.1:18765');
    expect(query.api).toBe('http://127.0.0.1:18765');
    expect(parseReviewQuery('?symbol=A&date=2026-09-18&api=http://evil.test').api).toBe('');
    expect(galleryFrame(['1m', '5m', '1d'])).toBe('5m');
    expect(galleryFrame(['1m', '1d'])).toBe('1m');
    expect(galleryFrame(['1d'])).toBe('5m');
    expect(reviewHref('A', '2026-09-18', ['5m'], '16:00', false, query.api)).toContain('api=http');
  });

  it('leaves blank time before 4:00 so the first clock label can draw', () => {
    const range = sessionVisibleRange('2026-09-18');
    expect(Number(range.to) - Number(range.from)).toBe(14 * 3600 + 10 * 60);
  });
});
