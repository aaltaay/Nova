/** A review day that cannot be loaded carries the route's code and words, so the page can show why. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchReview, REVIEW_PAGE_ERROR, ReviewLoadError, reviewLoadError } from './reviewData';
import { REVIEW_ORIGIN_LABELS, reviewPaneNote } from './reviewFeed';

function answer(status: number, body: unknown): void {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe('fetchReview errors', () => {
  it('keeps the code and the reason of a day no source holds', async () => {
    answer(404, { ok: false, code: 'REVIEW_NO_DATA', error: 'no minute file; the desk holds no candle' });
    const failure = await fetchReview('HIHO', '2026-11-14', ['1m'], '16:00').catch((reason: unknown) => reason);
    expect(failure).toBeInstanceOf(ReviewLoadError);
    expect((failure as ReviewLoadError).code).toBe('REVIEW_NO_DATA');
    expect((failure as ReviewLoadError).message).toBe('no minute file; the desk holds no candle');
  });

  it('names its own code when the answer names none', async () => {
    answer(500, { ok: false, error: 'RuntimeError: reader failed' });
    const failure = await fetchReview('HIHO', '2026-11-14', ['1m'], '16:00').catch((reason: unknown) => reason);
    expect((failure as ReviewLoadError).code).toBe(REVIEW_PAGE_ERROR);
    expect(reviewLoadError(new TypeError('Failed to fetch')).code).toBe(REVIEW_PAGE_ERROR);
  });
});

describe('a day read from the desk', () => {
  it('labels the panes and the header as IBKR, never as Massive', () => {
    expect(reviewPaneNote('1m', 'ibkr-history', false)).toBe('1m · IBKR history, from the desk');
    expect(reviewPaneNote('1d', 'ibkr-daily', false)).toBe('1d · IBKR daily bars, from the desk');
    expect(REVIEW_ORIGIN_LABELS['desk-ibkr']).toBe('IBKR, from the desk');
  });
});
