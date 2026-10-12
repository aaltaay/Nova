/**
 * @vitest-environment jsdom
 *
 * The held card's big-seller line (#846): the call with its hover, and the reason in plain words when there is no
 * read -- never an empty line; nothing at all from an API that has no such read.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { BigSellerLine } from './BigSellerLine';
import { normalizeBigWalls } from './bigSeller';

afterEach(cleanup);

const reading = (over: Record<string, unknown> = {}) => normalizeBigWalls({
  schema_version: 1, symbol: 'TEST', source: 'live', as_of: 100, watching: true, reason: null, last: 4.47, window: 0.05,
  sellers: [{ id: 'a', side: 'ask', price: 4.5, state: 'holding', size_first: 20_000, size_now: 20_000, traded: 0,
    multiple: 36, first_seen_ts: 58, seen_from_start: false, called_ts: 61, ended_ts: null, held_sec: 42,
    distance: 0.03, how: null, left: null }],
  buyers: [], sides: { ask: { levels: 5, enough: true }, bid: { levels: 4, enough: true } }, ...over,
});
const polled = (data: ReturnType<typeof reading>, error: string | null = null, unavailable = false) => (
  { data, loading: false, unavailable, error });

describe('the big-seller line', () => {
  it('shows the call, amber, with its words on hover', () => {
    render(<BigSellerLine big={polled(reading())} short={false} />);
    const line = screen.getByTestId('held-big');
    expect(line.textContent).toContain('BIG SELLER 20,000 @ 4.50 · 3¢ over · held 42 s');
    expect(line.className).toContain('sr-big--warn');
    expect(line.getAttribute('data-tip')).toMatch(/Shown, never acted on\./);
  });

  it('says why there is no read', () => {
    render(<BigSellerLine big={polled(reading({ watching: false, sellers: [],
      reason: 'No Level 2 line for TEST has reached the book watcher' }))} short={false} />);
    const line = screen.getByTestId('held-big');
    expect(line.textContent).toContain('No read on big sellers');
    expect(line.getAttribute('data-tip')).toBe('No Level 2 line for TEST has reached the book watcher');
  });

  it('draws nothing where the API has no such read', () => {
    render(<BigSellerLine big={polled(null, null, true)} short={false} />);
    expect(screen.queryByTestId('held-big')).toBeNull();
  });
});
